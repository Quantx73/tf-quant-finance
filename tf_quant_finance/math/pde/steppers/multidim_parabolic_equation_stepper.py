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
"""Stepper for multidimensional parabolic PDE solving."""

import numpy as np
import tensorflow.compat.v2 as tf


def multidim_parabolic_equation_step(
    time,
    next_time,
    coord_grid,
    value_grid,
    boundary_conditions,
    time_marching_scheme,
    second_order_coeff_fn=None,
    first_order_coeff_fn=None,
    zeroth_order_coeff_fn=None,
    inner_second_order_coeff_fn=None,
    inner_first_order_coeff_fn=None,
    dtype=None,
    name=None):
  """Performs one step in time to solve a multidimensional PDE.

  Typically one doesn't need to use this function directly, unless they have
  a custom time marching scheme. A simple stepper function for multidimensional
  PDEs can be found in `douglas_adi.py`.

  The PDE is of the form

  ```None
    dV/dt + Sum[a_ij d2(A_ij V)/dx_i dx_j, 1 <= i, j <=n] +
       Sum[b_i d(B_i V)/dx_i, 1 <= i <= n] + c V = 0.
  ```
  from time `t0` to time `t1`. The solver can go both forward and backward in
  time. Here `a_ij`, `A_ij`, `b_i`, `B_i` and `c` are coefficients that may
  depend on spatial variables `x` and time `t`.

  Here `V` is the unknown function, `V_{...}` denotes partial derivatives
  w.r.t. dimensions specified in curly brackets, `i` and `j` denote spatial
  dimensions, `r` is the spatial radius-vector.

  Args:
    time: Real scalar `Tensor`. The time before the step.
    next_time: Real scalar `Tensor`. The time after the step.
    coord_grid: List of `n` rank 1 real `Tensor`s. `n` is the dimension of the
      domain. The i-th `Tensor` has shape, `[d_i]` where `d_i` is the size of
      the grid along axis `i`. The coordinates of the grid points. Corresponds
      to the spatial grid `G` above.
    value_grid: Real `Tensor` containing the function values at time
      `time` which have to be evolved to time `next_time`. The shape of the
      `Tensor` must broadcast with `B + [d_1, d_2, ..., d_n]`. `B` is the batch
      dimensions (one or more), which allow multiple functions (with potentially
      different boundary/final conditions and PDE coefficients) to be evolved
      simultaneously.
    boundary_conditions: The boundary conditions. Only rectangular boundary
      conditions are supported.
      A list of tuples of size `n` (space dimension
      of the PDE). Each tuple consists of two callables representing the
      boundary conditions at the minimum and maximum values of the spatial
      variable indexed by the position in the list. E.g. for `n=2`, the length
      of `boundary_conditions` should be 2, `boundary_conditions[0][0]`
      describes the boundary `(y_min, x)`, and `boundary_conditions[1][0]`- the
      boundary `(y, x_min)`. The boundary conditions are accepted in the form
      `alpha(t, x) V + beta(t, x) V_n = gamma(t, x)`, where `V_n` is the
      derivative with respect to the exterior normal to the boundary.
      Each callable receives the current time `t` and the `coord_grid` at the
      current time, and should return a tuple of `alpha`, `beta`, and `gamma`.
      Each can be a number, a zero-rank `Tensor` or a `Rensor` whose shape is
      the grid shape with the corresponding dimension removed.
      For example, for a two-dimensional grid of shape `(b, ny, nx)`, where `b`
      is the batch size, `boundary_conditions[0][0]` should return a tuple of
      either numbers, zero-rank tensors or tensors of shape `(b, nx)`. Similarly
      for `boundary_conditions[1][0]`, except the tensor shape should be
      `(b, ny)`. `alpha` and `beta` can also be `None` in case of Neumann and
      Dirichlet conditions, respectively.
    time_marching_scheme: A callable which represents the time marching scheme
      for solving the PDE equation. If `u(t)` is space-discretized vector of the
      solution of a PDE, a time marching scheme approximately solves the
      equation `du/dt = A(t) u(t) + b(t)` for `u(t2)` given `u(t1)`, or vice
      versa if going backwards in time. Here `A` is a banded matrix containing
      contributions from the current and neighboring points in space, `b` is an
      arbitrary vector (inhomogeneous term).
      Multidimensional time marching schemes are usually based on the idea of
      ADI (alternating direction implicit) method: the time step is split into
      substeps, and in each substep only one dimension is treated "implicitly",
      while all the others are treated "explicitly". This way one has to solve
      only tridiagonal systems of equations, but not more complicated banded
      ones. A few examples of time marching schemes (Douglas, Craig-Sneyd, etc.)
      can be found in [1].
      The callable consumes the following arguments by keyword:
        1. inner_value_grid: Grid of solution values at the current time of
          the same `dtype` as `value_grid` and shape of `value_grid[..., 1:-1]`.
        2. t1: Lesser of the two times defining the step.
        3. t2: Greater of the two times defining the step.
        4. equation_params_fn: A callable that takes a scalar `Tensor` argument
          representing time and returns a tuple of two elements.
          The first one represents `A`. The length must be the number of
          dimensions (`n_dims`), and A[i] must have length `n_dims - i`.
          `A[i][0]` is a tridiagonal matrix representing influence of the
          neighboring points along the dimension `i`. It is a tuple of
          superdiagonal, diagonal, and subdiagonal parts of the tridiagonal
          matrix. The shape of these tensors must be same as of `value_grid`.
          superdiagonal[..., -1] and subdiagonal[..., 0] are ignored.
          `A[i][j]` with `i < j < n_dims` are tuples of four Tensors with same
          shape as `value_grid` representing the influence of four points placed
          diagonally from the given point in the plane of dimensions `i` and
          `j`. Denoting `k`, `l` the indices of a given grid point in the plane,
          the four Tensors represent contributions of points `(k+1, l+1)`,
          `(k+1, l-1)`, `(k-1, l+1)`, and `(k-1, l-1)`, in this order.
          The second element in the tuple is a list of contributions to `b(t)`
          associated with each dimension. E.g. if `b(t)` comes from boundary
          conditions, then it is split correspondingly. Each element in the list
          is a Tensor with the shape of `value_grid`.
          For example a 2D problem with `value_grid.shape = (B, ny, nx)`, where
          `B` is the batch size. The elements `Aij` are non-zero if `i = j` or
          `i` is a neighbor of `j` in the x-y plane. Depict these non-zero
          elements on the grid as follows:
          ```
          a_mm    a_y-   a_mp
          a_x-    a_0    a_x+
          a_pm   a_y+   a_pp
          ```
          The callable should return
          ```
          ([[(a_y-, a_0y, a_y+), (a_pp, a_pm, a_mp, a_pp)],
            [None, (a_x-, a_0x, a_x+)]],
          [b_y, b_x])
          ```
          where `a_0x + a_0y = a_0` (the splitting is arbitrary). Note that
          there is no need to repeat the non-diagonal term
          `(a_pp, a_pm, a_mp, a_pp)` for the second time: it's replaced with
          `None`.
          All the elements `a_...` may be different for each point in the grid,
          so they are `Tensors` of shape `(B, ny, nx)`. `b_y` and `b_x` are also
          `Tensors` of that shape.
        5. n_dims: A Python integer, the spatial dimension of the PDE.
      The callable should return a `Tensor` of the same shape and `dtype` as
      `values_grid` that represents an approximate solution of the
      space-discretized PDE.
    second_order_coeff_fn: Callable returning the second order coefficient
      `a_{ij}(t, r)` evaluated at given time `t`.
      The callable accepts the following arguments:
        `t`: The time at which the coefficient should be evaluated.
        `locations_grid`: a `Tensor` representing a grid of locations `r` at
          which the coefficient should be evaluated.
      Returns an object `A` such that `A[i][j]` is defined and
      `A[i][j]=a_{ij}(r, t)`, where `0 <= i < n_dims` and `i <= j < n_dims`.
      For example, the object may be a list of lists or a rank 2 Tensor.
      Only the elements with `j >= i` will be used, and it is assumed that
      `a_{ji} = a_{ij}`, so `A[i][j] with `j < i` may return `None`.
      Each `A[i][j]` should be a Number, a `Tensor` broadcastable to the
      shape of the grid represented by `locations_grid`, or `None` if
      corresponding term is absent in the equation. Also, the callable itself
      may be None, meaning there are no second-order derivatives in the
      equation.
      For example, for `n_dims=2`, the callable may return either
      `[[a_yy, a_xy], [a_xy, a_xx]]` or `[[a_yy, a_xy], [None, a_xx]]`.
    first_order_coeff_fn: Callable returning the first order coefficients
      `b_{i}(t, r)` evaluated at given time `t`.
      The callable accepts the following arguments:
        `t`: The time at which the coefficient should be evaluated.
        `locations_grid`: a `Tensor` representing a grid of locations `r` at
          which the coefficient should be evaluated.
      Returns a list or an 1D `Tensor`, `i`-th element of which represents
      `b_{i}(t, r)`. Each element should be a Number, a `Tensor` broadcastable
       to the shape of of the grid represented by `locations_grid`, or None if
       corresponding term is absent in the equation. The callable itself may be
       None, meaning there are no first-order derivatives in the equation.
    zeroth_order_coeff_fn: Callable returning the zeroth order coefficient
      `c(t, r)` evaluated at given time `t`.
      The callable accepts the following arguments:
        `t`: The time at which the coefficient should be evaluated.
        `locations_grid`: a `Tensor` representing a grid of locations `r` at
          which the coefficient should be evaluated.
      Should return a Number or a `Tensor` broadcastable to the shape of
      the grid represented by `locations_grid`. May also return None or be None
      if the shift term is absent in the equation.
    inner_second_order_coeff_fn: Callable returning the coefficients under the
      second derivatives (i.e. `A_ij(t, x)` above) at given time `t`. The
      requirements are the same as for `second_order_coeff_fn`.
    inner_first_order_coeff_fn: Callable returning the coefficients under the
      first derivatives (i.e. `B_i(t, x)` above) at given time `t`. The
      requirements are the same as for `first_order_coeff_fn`.
    dtype: The dtype to use.
    name: The name to give to the ops.
      Default value: None which means `parabolic_equation_step` is used.

  Returns:
    A sequence of two `Tensor`s. The first one is a `Tensor` of the same
    `dtype` and `shape` as `coord_grid` and represents a new coordinate grid
    after one iteration. The second `Tensor` is of the same shape and `dtype`
    as`values_grid` and represents an approximate solution of the equation after
    one iteration.

  #### References:
  [1] Tinne Haentjens, Karek J. in't Hout. ADI finite difference schemes
  for the Heston-Hull-White PDE. https://arxiv.org/abs/1111.4087
  """
  with tf.compat.v1.name_scope(
      name, 'multidim_parabolic_equation_step',
      values=[time, next_time, coord_grid, value_grid]):

    time = tf.convert_to_tensor(time, dtype=dtype, name='time')
    next_time = tf.convert_to_tensor(next_time, dtype=dtype, name='next_time')
    coord_grid = [tf.convert_to_tensor(x, dtype=dtype,
                                       name='coord_grid_axis_{}'.format(ind))
                  for ind, x in enumerate(coord_grid)]
    value_grid = tf.convert_to_tensor(value_grid, dtype=dtype,
                                      name='value_grid')

    n_dims = len(coord_grid)

    # Sanitize the coeff callables.
    second_order_coeff_fn = (second_order_coeff_fn or
                             (lambda *args: [[None] * n_dims] * n_dims))
    first_order_coeff_fn = (first_order_coeff_fn or
                            (lambda *args: [None] * n_dims))
    zeroth_order_coeff_fn = zeroth_order_coeff_fn or (lambda *args: None)
    inner_second_order_coeff_fn = (
        inner_second_order_coeff_fn or
        (lambda *args: [[None] * n_dims] * n_dims))
    inner_first_order_coeff_fn = (
        inner_first_order_coeff_fn or (lambda *args: [None] * n_dims))

    batch_rank = len(value_grid.shape.as_list()) - len(coord_grid)

    def equation_params_fn(t):
      return _construct_discretized_equation_params(
          coord_grid, value_grid, boundary_conditions, second_order_coeff_fn,
          first_order_coeff_fn, zeroth_order_coeff_fn,
          inner_second_order_coeff_fn, inner_first_order_coeff_fn, batch_rank,
          t)

    inner_grid_in = _trim_boundaries(value_grid, batch_rank)

    def _append_boundaries_fn(inner_value_grid):
      return _append_boundaries(
          value_grid, inner_value_grid, coord_grid, boundary_conditions,
          batch_rank, time)

    inner_grid_out = time_marching_scheme(
        value_grid=inner_grid_in,
        t1=time,
        t2=next_time,
        equation_params_fn=equation_params_fn,
        append_boundaries_fn=_append_boundaries_fn,
        n_dims=n_dims)

    updated_value_grid = _append_boundaries(
        value_grid, inner_grid_out, coord_grid, boundary_conditions, batch_rank,
        next_time)

    return coord_grid, updated_value_grid


def _construct_discretized_equation_params(
    coord_grid, value_grid, boundary_conditions, second_order_coeff_fn,
    first_order_coeff_fn, zeroth_order_coeff_fn, inner_second_order_coeff_fn,
    inner_first_order_coeff_fn, batch_rank, t):
  """Constructs parameters of discretized equation."""
  second_order_coeffs = second_order_coeff_fn(t, coord_grid)
  first_order_coeffs = first_order_coeff_fn(t, coord_grid)
  zeroth_order_coeffs = zeroth_order_coeff_fn(t, coord_grid)
  inner_second_order_coeffs = inner_second_order_coeff_fn(t, coord_grid)
  inner_first_order_coeffs = inner_first_order_coeff_fn(t, coord_grid)

  matrix_params = []
  inhomog_terms = []

  zeroth_order_coeffs = _prepare_pde_coeff(zeroth_order_coeffs, value_grid)
  if zeroth_order_coeffs is not None:
    zeroth_order_coeffs = _trim_boundaries(
        zeroth_order_coeffs, from_dim=batch_rank)

  n_dims = len(coord_grid)
  for dim in range(n_dims):
    # 1. Construct contributions of dV/dx_dim and d^2V/dx_dim^2. This yields
    # a tridiagonal matrix.
    delta = _get_grid_delta(coord_grid, dim)  # Non-uniform grids not supported.

    second_order_coeff = second_order_coeffs[dim][dim]
    first_order_coeff = first_order_coeffs[dim]
    inner_second_order_coeff = inner_second_order_coeffs[dim][dim]
    inner_first_order_coeff = inner_first_order_coeffs[dim]

    superdiag, diag, subdiag = (
        _construct_tridiagonal_matrix(value_grid, second_order_coeff,
                                      first_order_coeff,
                                      inner_second_order_coeff,
                                      inner_first_order_coeff, delta, dim,
                                      batch_rank, n_dims))

    # 2. Account for boundary conditions on boundaries orthogonal to dim.
    # This modifies the first and last row of the tridiagonal matrix and also
    # yields a contribution to the inhomogeneous term
    (superdiag, diag, subdiag), inhomog_term_contribution = (
        _apply_boundary_conditions_to_tridiagonal_and_inhomog_terms(
            value_grid, dim, batch_rank, boundary_conditions, coord_grid,
            superdiag, diag, subdiag, delta, t))

    # 3. Evenly distribute shift term among tridiagonal matrices of each
    # dimension. The minus sign is because we move the shift term to rhs.
    if zeroth_order_coeffs is not None:
      # pylint: disable=invalid-unary-operand-type
      diag += -zeroth_order_coeffs / n_dims

    matrix_params_row = [None] * dim + [(superdiag, diag, subdiag)]

    # 4. Construct contributions of mixed terms, d^2V/(dx_dim dx_dim2).
    for dim2 in range(dim + 1, n_dims):
      mixed_coeff = second_order_coeffs[dim][dim2]
      inner_mixed_coeff = inner_second_order_coeffs[dim][dim2]
      mixed_term_contrib = (
          _construct_contribution_of_mixed_term(mixed_coeff, inner_mixed_coeff,
                                                coord_grid, value_grid, dim,
                                                dim2, batch_rank, n_dims))
      matrix_params_row.append(mixed_term_contrib)

    matrix_params.append(matrix_params_row)
    inhomog_terms.append(inhomog_term_contribution)

  return matrix_params, inhomog_terms


def _construct_tridiagonal_matrix(value_grid, second_order_coeff,
                                  first_order_coeff, inner_second_order_coeff,
                                  inner_first_order_coeff, delta, dim,
                                  batch_rank, n_dims):
  """Constructs contributions of first and non-mixed second order terms."""
  second_order_coeff = _prepare_pde_coeff(second_order_coeff, value_grid)
  first_order_coeff = _prepare_pde_coeff(first_order_coeff, value_grid)
  inner_second_order_coeff = _prepare_pde_coeff(inner_second_order_coeff,
                                                value_grid)
  inner_first_order_coeff = _prepare_pde_coeff(inner_first_order_coeff,
                                               value_grid)

  zeros = tf.zeros_like(value_grid)
  zeros = _trim_boundaries(zeros, from_dim=batch_rank)

  def create_trimming_shifts(dim_shift):
    # See _trim_boundaries. We need to apply shift only to the dimension `dim`.
    shifts = [0] * n_dims
    shifts[dim] = dim_shift
    return shifts

  # Discretize first-order term.
  if first_order_coeff is None and inner_first_order_coeff is None:
    # No first-order term.
    superdiag_first_order = zeros
    diag_first_order = zeros
    subdiag_first_order = zeros
  else:
    superdiag_first_order = -1 / (2 * delta)
    subdiag_first_order = 1 / (2 * delta)
    diag_first_order = -superdiag_first_order - subdiag_first_order
    if first_order_coeff is not None:
      first_order_coeff = _trim_boundaries(
          first_order_coeff, from_dim=batch_rank)
      superdiag_first_order *= first_order_coeff
      subdiag_first_order *= first_order_coeff
      diag_first_order *= first_order_coeff
    if inner_first_order_coeff is not None:
      superdiag_first_order *= _trim_boundaries(
          inner_first_order_coeff,
          from_dim=batch_rank,
          shifts=create_trimming_shifts(1))
      subdiag_first_order *= _trim_boundaries(
          inner_first_order_coeff,
          from_dim=batch_rank,
          shifts=create_trimming_shifts(-1))
      diag_first_order *= _trim_boundaries(
          inner_first_order_coeff, from_dim=batch_rank)

  # Discretize second-order term.
  if second_order_coeff is None and inner_second_order_coeff is None:
    # No second-order term.
    superdiag_second_order = zeros
    diag_second_order = zeros
    subdiag_second_order = zeros
  else:
    superdiag_second_order = -1 / (delta * delta)
    subdiag_second_order = -1 / (delta * delta)
    diag_second_order = -superdiag_second_order - subdiag_second_order
    if second_order_coeff is not None:
      second_order_coeff = _trim_boundaries(
          second_order_coeff, from_dim=batch_rank)
      superdiag_second_order *= second_order_coeff
      subdiag_second_order *= second_order_coeff
      diag_second_order *= second_order_coeff
    if inner_second_order_coeff is not None:
      superdiag_second_order *= _trim_boundaries(
          inner_second_order_coeff,
          from_dim=batch_rank,
          shifts=create_trimming_shifts(1))
      subdiag_second_order *= _trim_boundaries(
          inner_second_order_coeff,
          from_dim=batch_rank,
          shifts=create_trimming_shifts(-1))
      diag_second_order *= _trim_boundaries(
          inner_second_order_coeff, from_dim=batch_rank)

  superdiag = superdiag_first_order + superdiag_second_order
  subdiag = subdiag_first_order + subdiag_second_order
  diag = diag_first_order + diag_second_order
  return superdiag, diag, subdiag


def _construct_contribution_of_mixed_term(
    outer_coeff, inner_coeff, coord_grid, value_grid,
    dim1, dim2, batch_rank, n_dims):
  """Constructs contribution of a mixed derivative term."""
  if outer_coeff is None and inner_coeff is None:
    return None
  delta_dim1 = _get_grid_delta(coord_grid, dim1)
  delta_dim2 = _get_grid_delta(coord_grid, dim2)

  outer_coeff = _prepare_pde_coeff(outer_coeff, value_grid)
  inner_coeff = _prepare_pde_coeff(inner_coeff, value_grid)

  # The contribution of d2V/dx_dim1 dx_dim2 is
  # mixed_coeff / (4 * delta_dim1 * delta_dim2), but there is also
  # d2V/dx_dim2 dx_dim1, so the contribution is doubled.
  # Also, the minus is because of moving to the rhs.
  contrib = -1 / (2 * delta_dim1 * delta_dim2)

  if outer_coeff is not None:
    outer_coeff = _trim_boundaries(outer_coeff, batch_rank)
    contrib *= outer_coeff

  if inner_coeff is None:
    return contrib, -contrib, -contrib, contrib

  def create_trimming_shifts(dim1_shift, dim2_shift):
    # See _trim_boundaries. We need to apply shifts to dimensions dim1 and
    # dim2.
    shifts = [0] * n_dims
    shifts[dim1] = dim1_shift
    shifts[dim2] = dim2_shift
    return shifts

  # When there are inner coefficients in mixed terms, the contributions of four
  # diagonally placed points are significantly different. Below we use indices
  # "p" and "m" to denote shifts by +1 and -1 in grid indices on the
  # (dim1, dim2) plane. E.g. if the current point has grid indices (k, l),
  # contrib_pm is the contribution of the point (k + 1, l - 1).
  contrib_pp = contrib * _trim_boundaries(
      inner_coeff, from_dim=batch_rank, shifts=create_trimming_shifts(1, 1))
  contrib_pm = -contrib * _trim_boundaries(
      inner_coeff, from_dim=batch_rank, shifts=create_trimming_shifts(1, -1))
  contrib_mp = -contrib * _trim_boundaries(
      inner_coeff, from_dim=batch_rank, shifts=create_trimming_shifts(-1, 1))
  contrib_mm = contrib * _trim_boundaries(
      inner_coeff, from_dim=batch_rank, shifts=create_trimming_shifts(-1, -1))

  return contrib_pp, contrib_pm, contrib_mp, contrib_mm


def _get_bound_coeff(coord_grid,
                     value_grid,
                     boundary_conditions,
                     batch_rank,
                     dim, t):
  """Extracts boundary conditions in a form alpha V + beta V' = gamma."""
  alpha_l, beta_l, gamma_l = boundary_conditions[dim][0](t, coord_grid)
  alpha_u, beta_u, gamma_u = boundary_conditions[dim][1](t, coord_grid)

  alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u = (
      _prepare_boundary_conditions(b, value_grid, batch_rank, dim)
      for b in (alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u))

  def reshape_fn(bound_coeff):
    """Reshapes boundary coefficient."""
    # Say the grid shape is (b, nz, ny, nx), and dim = 1.
    # The boundary condition coefficients are expected to have shape
    # (b, nz, nx). We need to:
    # - Trim the boundaries: nz -> nz-2, nx -> nx-2, because we work with
    # the inner part of the grid here.
    # - Expand dimension batch_rank+dim=2, because broadcasting won't always
    # do this correctly in subsequent computations: if a has shape (5, 1) and
    # b has shape (5,) then a*b has shape (5, 5)!
    # Thus this function turns (b, nz, nx) into (b, nz-2, 1, nx-2).
    return _reshape_boundary_conds(
        bound_coeff, trim_from=batch_rank, expand_dim_at=batch_rank + dim)

  alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u = map(
      reshape_fn, (alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u))
  return alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u


def _apply_boundary_conditions_to_tridiagonal_and_inhomog_terms(
    value_grid, dim, batch_rank, boundary_conditions, coord_grid, superdiag,
    diag, subdiag, delta, t):
  """Updates contributions according to boundary conditions."""
  # This is analogous to _apply_boundary_conditions_to_discretized_equation in
  # pde_kernels.py. The difference is that we work with the given spatial
  # dimension. In particular, in all the tensor slices we have to slice
  # into the dimension `batch_rank + dim` instead of the last dimension.

  # Retrieve the boundary conditions in the form alpha V + beta V' = gamma.
  (
      alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u
  ) = _get_bound_coeff(coord_grid, value_grid,
                       boundary_conditions, batch_rank, dim, t)
  dim += batch_rank
  subdiag_first = _slice(subdiag, dim, 0, 1)
  superdiag_last = _slice(superdiag, dim, -1, 0)
  diag_inner = _slice(diag, dim, 1, -1)

  if beta_l is None and beta_u is None:
    # Dirichlet conditions on both boundaries. In this case there are no
    # corrections to the tridiagonal matrix, so we can take a shortcut.
    first_inhomog_element = subdiag_first * gamma_l / alpha_l
    last_inhomog_element = superdiag_last * gamma_u / alpha_u
    inhomog_term = _append_first_and_last(
        first_inhomog_element,
        tf.zeros_like(diag_inner),
        last_inhomog_element,
        axis=dim)
    return (superdiag, diag, subdiag), inhomog_term

  # A few more slices we're going to need.
  subdiag_last = _slice(subdiag, dim, -1, 0)
  subdiag_except_last = _slice(subdiag, dim, 0, -1)
  superdiag_first = _slice(superdiag, dim, 0, 1)
  superdiag_except_first = _slice(superdiag, dim, 1, 0)
  diag_first = _slice(diag, dim, 0, 1)
  diag_last = _slice(diag, dim, -1, 0)

  # Convert the boundary conditions into the form v0 = xi1 v1 + xi2 v2 + eta,
  # and calculate corrections to the tridiagonal matrix and the inhomogeneous
  # term.
  xi1, xi2, eta = _discretize_boundary_conditions(delta, delta, alpha_l,
                                                  beta_l, gamma_l)
  diag_first_correction = subdiag_first * xi1
  superdiag_correction = subdiag_first * xi2
  first_inhomog_element = subdiag_first * eta
  xi1, xi2, eta = _discretize_boundary_conditions(delta, delta, alpha_u,
                                                  beta_u, gamma_u)
  diag_last_correction = superdiag_last * xi1
  subdiag_correction = superdiag_last * xi2
  last_inhomog_element = superdiag_last * eta
  diag = _append_first_and_last(
      diag_first + diag_first_correction,
      diag_inner,
      diag_last + diag_last_correction, axis=dim)
  superdiag = _append_first(
      superdiag_first + superdiag_correction, superdiag_except_first,
      axis=dim)
  subdiag = _append_last(
      subdiag_except_last, subdiag_last + subdiag_correction, axis=dim)
  inhomog_term = _append_first_and_last(
      first_inhomog_element,
      tf.zeros_like(diag_inner),
      last_inhomog_element,
      axis=dim)
  return (superdiag, diag, subdiag), inhomog_term


def _append_boundaries(value_grid_in, inner_grid_out,
                       coord_grid, boundary_conditions,
                       batch_rank, t):
  """Calculates and appends boundary values after making a step."""
  # After we've updated the values in the inner part of the grid according to
  # the PDE, we append the boundary values calculated using the boundary
  # conditions.
  # This is done using the discretized form of the boundary conditions,
  # v0 = xi1 v1 + xi2 v2 + eta.
  # This is analogous to _append_boundaries in pde_kernels.py, except we have to
  # restore the boundaries in each dimension. For example, for n_dims=2,
  # inner_grid_out has dimensions (b, ny-2, nx-2), which then becomes
  # (b, ny, nx-2) and finally (b, ny, nx).
  grid = inner_grid_out
  for dim in range(len(coord_grid)):
    grid = _append_boundary(dim, batch_rank,
                            boundary_conditions,
                            coord_grid,
                            value_grid_in, grid, t)
  return grid


def _append_boundary(dim, batch_rank, boundary_conditions,
                     coord_grid, value_grid_in, current_value_grid_out, t):
  """Calculates and appends boundaries orthogonal to `dim`."""
  # E.g. for n_dims = 3, and dim = 1, the expected input grid shape is
  # (b, nx, ny-2, nz-2), and the output shape is (b, nx, ny, nz-2).
  lower_value_first = _slice(current_value_grid_out, batch_rank + dim, 0, 1)
  lower_value_second = _slice(current_value_grid_out, batch_rank + dim, 1, 2)
  upper_value_first = _slice(current_value_grid_out, batch_rank + dim, -1, 0)
  upper_value_second = _slice(current_value_grid_out, batch_rank + dim, -2, -1)

  alpha_l, beta_l, gamma_l = boundary_conditions[dim][0](t, coord_grid)
  alpha_u, beta_u, gamma_u = boundary_conditions[dim][1](t, coord_grid)

  alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u = (
      _prepare_boundary_conditions(b, value_grid_in, batch_rank, dim)
      for b in (alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u))

  def reshape_fn(bound_coeff):
    # Say the grid shape is (b, nz, ny-2, nx-2), and dim = 1: we have already
    # restored the z-boundaries and now are restoring the y-boundaries.
    # The boundary condition coefficients are expected to have the shape
    # (b, nz, nx). We need to:
    # - Trim the boundaries which we haven't yet restored: nx -> nx-2.
    # - Expand dimension batch_rank+dim=2, because broadcasting won't always
    # do this correctly in subsequent computations.
    # Thus this function turns (b, nz, nx) into (b, nz, 1, nx-2).
    return _reshape_boundary_conds(
        bound_coeff,
        trim_from=batch_rank + dim,
        expand_dim_at=batch_rank + dim)

  alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u = map(
      reshape_fn, (alpha_l, beta_l, gamma_l, alpha_u, beta_u, gamma_u))

  delta = _get_grid_delta(coord_grid, dim)
  xi1, xi2, eta = _discretize_boundary_conditions(delta, delta, alpha_l,
                                                  beta_l, gamma_l)
  first_value = (xi1 * lower_value_first + xi2 * lower_value_second + eta)
  xi1, xi2, eta = _discretize_boundary_conditions(delta, delta, alpha_u,
                                                  beta_u, gamma_u)
  last_value = (xi1 * upper_value_first + xi2 * upper_value_second + eta)
  return _append_first_and_last(first_value, current_value_grid_out, last_value,
                                axis=batch_rank + dim)


def _get_grid_delta(coord_grid, dim):
  # Retrieves delta along given dimension, assuming the grid is uniform.
  return coord_grid[dim][1] - coord_grid[dim][0]


def _prepare_pde_coeff(raw_coeff, value_grid):
  # Converts values received from second_order_coeff_fn and similar Callables
  # into a format usable further down in the pipeline.
  if raw_coeff is None:
    return None
  dtype = value_grid.dtype
  coeff = tf.convert_to_tensor(raw_coeff, dtype=dtype)
  coeff = tf.broadcast_to(coeff, tf.shape(value_grid))
  return coeff


def _prepare_boundary_conditions(boundary_tensor, value_grid, batch_rank, dim):
  """Prepares values received from boundary_condition callables."""
  if boundary_tensor is None:
    return None
  boundary_tensor = tf.convert_to_tensor(boundary_tensor, value_grid.dtype)
  # Broadcast to the shape of the boundary: it is the shape of value grid with
  # one dimension removed.
  dim_to_remove = batch_rank + dim
  broadcast_shape = []
  # Shape slicing+concatenation seems error-prone, so let's do it simply.
  for i, size in enumerate(value_grid.shape):
    if i != dim_to_remove:
      broadcast_shape.append(size)
  return tf.broadcast_to(boundary_tensor, broadcast_shape)


def _discretize_boundary_conditions(dx0, dx1, alpha, beta, gamma):
  """Discretizes boundary conditions."""
  # Converts a boundary condition given as alpha V + beta V_n = gamma,
  # where V_n is the derivative w.r.t. the normal to the boundary into
  # v0 = xi1 v1 + xi2 v2 + eta,
  # where v0 is the value on the boundary point of the grid, v1 and v2 - values
  # on the next two points on the grid.
  # The expressions are exactly the same for both boundaries.

  if beta is None:
    # Dirichlet condition.
    if alpha is None:
      raise ValueError(
          "Invalid boundary conditions: alpha and beta can't both be None.")
    zeros = tf.zeros_like(gamma)
    return zeros, zeros, gamma / alpha

  denom = beta * dx1 * (2 * dx0 + dx1)
  if alpha is not None:
    denom += alpha * dx0 * dx1 * (dx0 + dx1)
  xi1 = beta * (dx0 + dx1) * (dx0 + dx1) / denom
  xi2 = -beta * dx0 * dx0 / denom
  eta = gamma * dx0 * dx1 * (dx0 + dx1) / denom
  return xi1, xi2, eta


def _reshape_boundary_conds(raw_coeff, trim_from, expand_dim_at):
  """Reshapes boundary condition coefficients."""
  # If the coefficient is None, a number or a rank-0 tensor, return as-is.
  if (not tf.is_tensor(raw_coeff)
      or len(raw_coeff.shape.as_list()) == 0):  # pylint: disable=g-explicit-length-test
    return raw_coeff
  # See explanation why we trim boundaries and expand dims in places where this
  # function is used.
  coeff = _trim_boundaries(raw_coeff, trim_from)
  coeff = tf.expand_dims(coeff, expand_dim_at)
  return coeff


def _slice(tensor, dim, start, end):
  """Slices the tensor along given dimension."""
  # Performs a slice along the dimension dim. E.g. for tensor t of rank 3,
  # _slice(t, 1, 3, 5) is same as t[:, 3:5].
  # For a slice unbounded to the right, set end=0: _slice(t, 1, -3, 0) is same
  # as t[:, -3:].
  rank = tensor.shape.rank
  slices = rank * [slice(None)]
  if end == 0:
    end = None
  slices[dim] = slice(start, end)
  return tensor[slices]


def _trim_boundaries(tensor, from_dim, shifts=None):
  """Trims tensor boundaries starting from given dimension."""
  # For example, if tensor has shape (a, b, c, d) and from_dim=1, then the
  # output tensor has shape (a, b-2, c-2, d-2).
  # For example _trim_boundaries_with_shifts(t, 1) with a rank-4
  # tensor t yields t[:, 1:-1, 1:-1, 1:-1].
  #
  # If shifts is specified, the slices applied are shifted. shifts is an array
  # of length rank(tensor) - from_dim, with values -1, 0, or 1, meaning slices
  # [:-2], [-1, 1], and [2:], respectively.
  # For example _trim_boundaries_with_shifts(t, 1, (1, 0, -1)) with a rank-4
  #  tensor t yields t[:, 2:, 1:-1, :-2].
  rank = len(tensor.shape.as_list())
  slice_begin = np.zeros(rank, dtype=np.int32)
  slice_size = np.zeros(rank, dtype=np.int32)
  for i in range(from_dim):
    slice_size[i] = tf.compat.dimension_value(tensor.shape.as_list()[i])
  for i in range(from_dim, rank):
    slice_begin[i] = 1
    slice_size[i] = tf.compat.dimension_value(tensor.shape.as_list()[i]) - 2
    if shifts is not None:
      slice_begin[i] += shifts[i - from_dim]
  return tf.slice(tensor, slice_begin, slice_size)


def _append_first_and_last(first, inner, last, axis):
  if first is None:
    return _append_last(inner, last, axis=axis)
  if last is None:
    return _append_first(first, inner, axis=axis)
  return tf.concat((first, inner, last), axis=axis)


def _append_first(first, rest, axis):
  if first is None:
    return rest
  return tf.concat((first, rest), axis=axis)


def _append_last(rest, last, axis):
  if last is None:
    return rest
  return tf.concat((rest, last), axis=axis)


__all__ = ['multidim_parabolic_equation_step']
