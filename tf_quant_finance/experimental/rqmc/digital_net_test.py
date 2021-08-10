# Lint as: python3
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for digital nets."""

import tensorflow.compat.v2 as tf
import tf_quant_finance as tff

from tensorflow.python.framework import test_util  # pylint: disable=g-direct-tensorflow-import

rqmc = tff.experimental.rqmc


@test_util.run_all_in_graph_and_eager_modes
class DigitalNetTest(tf.test.TestCase):

  def test_random_scrambling_matrices(self):
    dim = 6
    num_digits = 3
    seed = (2, 3)

    actual = rqmc.random_scrambling_matrices(
        dim, num_digits, seed, validate_args=True)

    power = tf.constant(num_digits)
    minval = rqmc.utils.exp2(power - 1)
    maxval = rqmc.utils.exp2(power)

    self.assertEqual(actual.shape[0], dim)
    self.assertEqual(actual.shape[1], num_digits)
    self.assertEqual(actual.dtype, tf.int32)
    self.assertAllLess(actual, maxval)
    self.assertAllGreaterEqual(actual, minval)

  def test_random_scrambling_matrices_with_dtype(self):
    dim = 6
    num_digits = 3
    seed = (2, 3)

    for dtype in [tf.int32, tf.int64]:
      actual = rqmc.random_scrambling_matrices(
          dim, num_digits, seed, dtype=dtype, validate_args=True)

      power = tf.constant(num_digits, dtype=dtype)
      minval = rqmc.utils.exp2(power - 1)
      maxval = rqmc.utils.exp2(power)

      self.assertEqual(actual.shape[0], dim)
      self.assertEqual(actual.shape[1], num_digits)
      self.assertEqual(actual.dtype, dtype)
      self.assertAllLess(actual, maxval)
      self.assertAllGreaterEqual(actual, minval)

  def test_sample_digital_net(self):
    dim = 5
    num_results = 29
    num_digits = 5  # ceil(log2(num_results))

    for dtype in [tf.int32, tf.int64]:
      expected = tf.constant([[0.00000, 0.00000, 0.00000, 0.00000, 0.00000],
                              [0.50000, 0.50000, 0.50000, 0.50000, 0.50000],
                              [0.25000, 0.75000, 0.75000, 0.75000, 0.25000],
                              [0.75000, 0.25000, 0.25000, 0.25000, 0.75000],
                              [0.12500, 0.62500, 0.37500, 0.12500, 0.12500],
                              [0.62500, 0.12500, 0.87500, 0.62500, 0.62500],
                              [0.37500, 0.37500, 0.62500, 0.87500, 0.37500],
                              [0.87500, 0.87500, 0.12500, 0.37500, 0.87500],
                              [0.06250, 0.93750, 0.56250, 0.31250, 0.68750],
                              [0.56250, 0.43750, 0.06250, 0.81250, 0.18750],
                              [0.31250, 0.18750, 0.31250, 0.56250, 0.93750],
                              [0.81250, 0.68750, 0.81250, 0.06250, 0.43750],
                              [0.18750, 0.31250, 0.93750, 0.43750, 0.56250],
                              [0.68750, 0.81250, 0.43750, 0.93750, 0.06250],
                              [0.43750, 0.56250, 0.18750, 0.68750, 0.81250],
                              [0.93750, 0.06250, 0.68750, 0.18750, 0.31250],
                              [0.03125, 0.53125, 0.90625, 0.96875, 0.96875],
                              [0.53125, 0.03125, 0.40625, 0.46875, 0.46875],
                              [0.28125, 0.28125, 0.15625, 0.21875, 0.71875],
                              [0.78125, 0.78125, 0.65625, 0.71875, 0.21875],
                              [0.15625, 0.15625, 0.53125, 0.84375, 0.84375],
                              [0.65625, 0.65625, 0.03125, 0.34375, 0.34375],
                              [0.40625, 0.90625, 0.28125, 0.09375, 0.59375],
                              [0.90625, 0.40625, 0.78125, 0.59375, 0.09375],
                              [0.09375, 0.46875, 0.46875, 0.65625, 0.28125],
                              [0.59375, 0.96875, 0.96875, 0.15625, 0.78125],
                              [0.34375, 0.71875, 0.71875, 0.40625, 0.03125],
                              [0.84375, 0.21875, 0.21875, 0.90625, 0.53125],
                              [0.21875, 0.84375, 0.09375, 0.53125, 0.40625]],
                             dtype=tf.float32)

      actual = rqmc.sample_digital_net(
          rqmc.sobol_generating_matrices(
              dim, num_results, num_digits, dtype=dtype),
          num_results,
          num_digits,
          validate_args=True)

      self.assertAllClose(
          self.evaluate(actual), self.evaluate(expected), rtol=1e-6)
      self.assertEqual(actual.dtype, expected.dtype)

  def test_sample_digital_net_with_sequence_indices(self):
    dim = 5
    num_results = 29
    num_digits = 5  # ceil(log2(num_results))
    indices = [1, 3, 10, 15, 19, 24, 28]

    expected = tf.constant([[0.50000, 0.50000, 0.50000, 0.50000, 0.50000],
                            [0.75000, 0.25000, 0.25000, 0.25000, 0.75000],
                            [0.31250, 0.18750, 0.31250, 0.56250, 0.93750],
                            [0.93750, 0.06250, 0.68750, 0.18750, 0.31250],
                            [0.78125, 0.78125, 0.65625, 0.71875, 0.21875],
                            [0.09375, 0.46875, 0.46875, 0.65625, 0.28125],
                            [0.21875, 0.84375, 0.09375, 0.53125, 0.40625]],
                           dtype=tf.float32)

    actual = rqmc.sample_digital_net(
        rqmc.sobol_generating_matrices(dim, num_results, num_digits),
        num_results,
        num_digits,
        sequence_indices=tf.constant(indices, dtype=tf.int64),
        validate_args=True)

    self.assertAllClose(
        self.evaluate(actual), self.evaluate(expected), rtol=1e-6)
    self.assertEqual(actual.dtype, expected.dtype)

  def test_sample_sobol_with_tent_transform(self):
    dim = 6
    num_results = 8
    num_digits = 3  # ceil(log2(num_results))

    expected = tf.constant([[0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
                            [1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
                            [0.50, 0.50, 0.50, 0.50, 0.50, 0.50],
                            [0.50, 0.50, 0.50, 0.50, 0.50, 0.50],
                            [0.25, 0.75, 0.75, 0.25, 0.25, 0.75],
                            [0.75, 0.25, 0.25, 0.75, 0.75, 0.25],
                            [0.75, 0.75, 0.75, 0.25, 0.75, 0.25],
                            [0.25, 0.25, 0.25, 0.75, 0.25, 0.75]],
                           dtype=tf.float32)

    actual = rqmc.sample_digital_net(
        rqmc.sobol_generating_matrices(dim, num_results, num_digits),
        num_results,
        num_digits,
        apply_tent_transform=True,
        validate_args=True)

    self.assertAllClose(
        self.evaluate(actual), self.evaluate(expected), rtol=1e-6)
    self.assertEqual(actual.dtype, expected.dtype)

  def test_sample_digital_net_with_dtype(self):
    dim = 5
    num_results = 6
    num_digits = 3  # ceil(log2(num_results))

    generating_matrices = rqmc.sobol_generating_matrices(
        dim, num_results, num_digits)

    for dtype in [tf.float32, tf.float64]:
      expected = tf.constant([[0.000, 0.000, 0.000, 0.000, 0.000],
                              [0.500, 0.500, 0.500, 0.500, 0.500],
                              [0.250, 0.750, 0.750, 0.750, 0.250],
                              [0.750, 0.250, 0.250, 0.250, 0.750],
                              [0.125, 0.625, 0.375, 0.125, 0.125],
                              [0.625, 0.125, 0.875, 0.625, 0.625]],
                             dtype=dtype)

      actual = rqmc.sample_digital_net(
          generating_matrices,
          num_results,
          num_digits,
          validate_args=True,
          dtype=dtype)

      self.assertAllClose(
          self.evaluate(actual), self.evaluate(expected), rtol=1e-6)
      self.assertEqual(actual.dtype, expected.dtype)

  def test_scramble_generating_matrices(self):
    dim = 6
    num_results = 8
    num_digits = 3  # ceil(log2(num_results))
    seed = (2, 3)

    for dtype in [tf.int32, tf.int64]:
      generating_matrices = rqmc.sobol_generating_matrices(
          dim, num_results, num_digits, dtype=dtype)

      scrambling_matrices = rqmc.random_scrambling_matrices(
          dim, num_digits, seed)

      actual = rqmc.scramble_generating_matrices(
          generating_matrices,
          scrambling_matrices,
          num_digits,
          validate_args=True)

      self.assertEqual(actual.shape, generating_matrices.shape)
      self.assertEqual(actual.dtype, dtype)

  def test_scramble_generating_matrices_with_minimum_scrambling_matrices(self):
    dim = 6
    num_results = 8
    num_digits = 3  # ceil(log2(num_results))

    for dtype in [tf.int32, tf.int64]:
      generating_matrices = rqmc.sobol_generating_matrices(
          dim, num_results, num_digits, dtype=dtype)

      # All scrambling matrices values are between 2^{num_digits - 1} (incl.)
      # and 2^{num_digits} (excl.). Scrambling using matrices for which all
      # values are set to 2^{num_digits - 1} should be a no-op.
      min_scrambling_matrices = tf.broadcast_to(
          rqmc.utils.exp2(tf.cast(num_digits, dtype) - 1),
          shape=generating_matrices.shape)

      actual = rqmc.scramble_generating_matrices(
          generating_matrices,
          min_scrambling_matrices,
          num_digits,
          dtype=dtype,
          validate_args=True)

      print('Actual: ', actual)
      self.assertEqual(actual.shape, generating_matrices.shape)
      self.assertEqual(actual.dtype, generating_matrices.dtype)
      self.assertAllEqual(
          self.evaluate(actual), self.evaluate(generating_matrices))

  def test_scramble_generating_matrices_with_dtype(self):
    dim = 6
    num_results = 8
    num_digits = 3  # ceil(log2(num_results))
    seed = (2, 3)

    generating_matrices = rqmc.sobol_generating_matrices(
        dim, num_results, num_digits)

    scrambling_matrices = rqmc.random_scrambling_matrices(dim, num_digits, seed)

    for dtype in [tf.int32, tf.int64]:
      actual = rqmc.scramble_generating_matrices(
          generating_matrices,
          scrambling_matrices,
          num_digits,
          dtype=dtype,
          validate_args=True)

      self.assertEqual(actual.shape, generating_matrices.shape)
      self.assertEqual(actual.dtype, dtype)


if __name__ == '__main__':
  tf.test.main()
