#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2017 Judit Acs <judit@sch.bme.hu>
#
# Distributed under terms of the MIT license.
from __future__ import unicode_literals

import os
import numpy as np
import json


class DataSet(object):
    def __init__(self):
        self.vocab_enc = {"": 0}
        self.vocab_dec = {"": 0}
        self.samples = []

    def read_data_from_stream(self, stream, delimiter='', limit=0):
        for line in stream:
            # dirty hack for Python 2 support
            try:
                line = line.decode("utf8")
            except AttributeError:
                pass
            if not line.strip():
                continue
            enc, dec = line.rstrip('\n').split('\t')
            if limit > 0 and len(self.samples) > limit:
                break
            if delimiter:
                self.samples.append((enc.split(delimiter),
                                     dec.split(delimiter)))
            else:
                self.samples.append((list(enc), list(dec)))

    def vectorize_samples(self, frozen=False):
        data_enc = []
        data_dec = []
        try:
            self.maxlen_enc
        except AttributeError:
            self.maxlen_enc = max(len(s[0]) for s in self.samples)
        try:
            self.maxlen_dec
        except AttributeError:
            self.maxlen_dec = max(len(s[1]) for s in self.samples) + 2
        dec_pad_length = self.maxlen_dec - 2
        for enc, dec in self.samples:
            padded = ['PAD' for p in range(self.maxlen_enc - len(enc))] + enc
            if frozen:
                data_enc.append(
                    [self.vocab_enc.get(c, 0)
                     for c in padded]
                )
            else:
                data_enc.append(
                    [self.vocab_enc.setdefault(c, len(self.vocab_enc))
                     for c in padded]
                )
            padded = ['GO'] + dec + \
                ['PAD' for p in range(dec_pad_length - len(dec))] + ['STOP']
            if frozen:
                data_dec.append(
                    [self.vocab_dec.get(c, 0)
                     for c in padded]
                )
            else:
                data_dec.append(
                    [self.vocab_dec.setdefault(c, len(self.vocab_dec))
                     for c in padded]
                )
        self.data_enc = np.array(data_enc)
        self.data_dec = np.array(data_dec)

    def split_train_valid_test(self, valid_ratio=.1, test_ratio=.1):
        N = self.data_enc.shape[0]
        if N < 3:
            raise ValueError("Must have at least 3 training examples")
        if N * valid_ratio < 1:
            valid_ratio = 1.0 / N
        if N * test_ratio < 1:
            test_ratio = 1.0 / N
        train_end = int((1 - valid_ratio - test_ratio) * N)
        valid_end = int((1 - test_ratio) * N)
        shuf_ind = np.arange(N)
        np.random.shuffle(shuf_ind)
        self.train_idx = shuf_ind[:train_end]
        self.valid_idx = shuf_ind[train_end:valid_end]
        self.test_idx = shuf_ind[valid_end:]
        self.data_enc_train = self.data_enc[self.train_idx]
        self.data_dec_train = self.data_dec[self.train_idx]
        self.data_enc_valid = self.data_enc[self.valid_idx]
        self.data_dec_valid = self.data_dec[self.valid_idx]
        self.data_enc_test = self.data_enc[self.test_idx]
        self.data_dec_test = self.data_dec[self.test_idx]

    def get_batch(self, batch_size):
        try:
            self.data_enc
        except AttributeError:
            self.vectorize_samples()
        indices = np.random.choice(self.data_enc_train.shape[0], batch_size)
        return self.data_enc_train[indices], self.data_dec_train[indices]

    def to_dict(self):
        d = {
            'enc_shape': self.data_enc.shape,
            'dec_shape': self.data_dec.shape,
            'train_enc_shape': self.data_enc_train.shape,
            'train_dec_shape': self.data_dec_train.shape,
            'val_enc_shape': self.data_enc_valid.shape,
            'val_dec_shape': self.data_dec_valid.shape,
            'test_enc_shape': self.data_enc_test.shape,
            'test_dec_shape': self.data_dec_test.shape,
        }
        labels, counts = np.unique(self.data_dec, return_counts=True)
        inv_vocab = {v: k for k, v in self.vocab_dec.items()}
        classes = dict(zip(map(inv_vocab.get, labels), counts))
        d['label_counts'] = classes
        return d

    def __get_samples(self, idx, include_input=False):
        if include_input is True:
            return [
                (''.join(self.samples[i][0]), ''.join(self.samples[i][1]))
                for i in idx
            ]
        else:
            return [''.join(self.samples[i][0]) for i in idx]

    def get_train_samples(self):
        return self.__get_samples(self.train_idx, False)

    def get_valid_samples(self):
        return self.__get_samples(self.valid_idx, False)

    def get_test_samples(self, include_test_input=False):
        return self.__get_samples(self.test_idx, include_test_input)

    def save_vocabularies(self, model_dir):
        enc_fn = os.path.join(model_dir, 'encoding_vocab')
        DataSet.write_dict_to_file(self.vocab_enc, enc_fn)
        dec_fn = os.path.join(model_dir, 'decoding_vocab')
        DataSet.write_dict_to_file(self.vocab_dec, dec_fn)

    def save_params(self, model_dir):
        fn = os.path.join(model_dir, 'dataset_params.json')
        d = {
            'maxlen_enc': self.maxlen_enc,
            'maxlen_dec': self.maxlen_enc,
        }
        with open(fn, 'w') as f:
            json.dump(d, f)

    @staticmethod
    def write_dict_to_file(dict_, filename):
        with open(filename, 'w') as f:
            try:
                f.write('\n'.join(
                    '{}\t{}'.format(k, v) for k, v in dict_.items()
                ).encode('utf8'))
            except TypeError:
                f.write('\n'.join(
                    '{}\t{}'.format(k, v) for k, v in dict_.items()
                ))


class EncoderInput(DataSet):
    """Encoder input without output.
    This class should be used for inference,
    when gold standard decoding data is not available.
    """
    def __init__(self, model_dir):
        enc_vocab_fn = os.path.join(model_dir, 'encoding_vocab')
        self.vocab_enc = read_vocab(enc_vocab_fn)
        dec_vocab_fn = os.path.join(model_dir, 'decoding_vocab')
        self.vocab_dec = read_vocab(dec_vocab_fn)
        conf_fn = os.path.join(model_dir, 'dataset_params.json')
        self.load_params(conf_fn)
        self.samples = []

    def load_params(self, fn):
        with open(fn) as f:
            for param, val in json.load(f).items():
                setattr(self, param, val)

    def read_data_from_stream(self, stream, delimiter='', limit=0):
        """Reads unlabeled data from a stream"""
        for line in stream:
            try:
                line = line.decode("utf8")
            except AttributeError:
                pass
            if not line.strip():
                continue
            enc = line.rstrip('\n')
            if limit > 0 and len(self.samples) > limit:
                break
            if len(enc) > self.maxlen_enc:
                enc = enc[-self.maxlen_enc:]
            if delimiter:
                self.samples.append((enc.split(delimiter), ''))
            else:
                self.samples.append((list(enc), list('')))

    @property
    def test_idx(self):
        return range(len(self.samples))


def read_vocab(filename):
    with open(filename) as f:
        vocab = {}
        for line in f:
            try:
                fd = line.decode('utf8').split('\t')
            except AttributeError:
                fd = line.split('\t')
            vocab[fd[0]] = int(fd[1])
        return vocab
