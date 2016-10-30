# -*- coding: utf-8 -*-
"""
===============================
Poisson (Softplus) Distribution
===============================

For Poisson distributed target variables, the canonical link function is an
exponential nonlinearity. However, the gradient of the loss function that uses
this nonlinearity is typically unstable.

This is an example demonstrating how pyglmnet
works with a Poisson distribution using the softplus nonlinearity.

Here, for the ``distr = 'softplus'`` option, we use the
softplus function: ``log(1+exp())``.

"""

########################################################
# First, let's import useful libraries that we will use it later on.

########################################################

# Author: Pavan Ramkumar <pavan.ramkumar@gmail.com>
# License: MIT

import numpy as np
import scipy.sparse as sps
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt

########################################################
# Here are inputs that you can provide when you instantiate the `GLM` class.
# If not provided, it will be set to the respective defaults
#
# - `distr`: str (`'softplus'` or `'poisson'` or `'gaussian'` or `'binomial'` or `'multinomial'`)
#     default: `'poisson'`
# - `alpha`: float (the weighting between L1 and L2 norm)
#     default: 0.05
# - `reg_lambda`: array (array of regularization parameters)
#     default: `np.logspace(np.log(0.5), np.log(0.01), 10, base=np.exp(1))`
# - `learning_rate`: float (learning rate for gradient descent)
#     default: 2e-1
# - `max_iter`: int (maximum iteration for the model)
#     default: 1000

########################################################

########################################################
# Import ``GLM`` class from ``pyglmnet``

########################################################

# import GLM model
from pyglmnet import GLM

# create regularization parameters for model
reg_lambda = np.logspace(np.log(0.5), np.log(0.01), 10, base=np.exp(1))
glm_poisson = GLM(distr='softplus', verbose=False, alpha=0.05,
            max_iter=1000, learning_rate=2e-1,
            reg_lambda=reg_lambda)

##########################################################
# Simulate a dataset
# ------------------
# The ``GLM`` class has a very useful method called ``simulate()``.
#
# Since a canonical link function is already specified by the distribution
# parameters, or provided by the user, ``simulate()`` requires
# only the independent variables ``X`` and the coefficients ``beta0``
# and ``beta``

##########################################################

n_samples, n_features = 10000, 100

# coefficients
beta0 = np.random.normal(0.0, 1.0, 1)
beta = sps.rand(n_features, 1, 0.1)
beta = np.array(beta.todense())

# training data
Xr = np.random.normal(0.0, 1.0, [n_samples, n_features])
yr = glm_poisson.simulate(beta0, beta, Xr)

# testing data
Xt = np.random.normal(0.0, 1.0, [n_samples, n_features])
yt = glm_poisson.simulate(beta0, beta, Xt)

##########################################################
# Fit the model
# ^^^^^^^^^^^^^
# Fitting the model is accomplished by a single GLM method called `fit()`.

##########################################################

scaler = StandardScaler().fit(Xr)
glm_poisson.fit(scaler.transform(Xr), yr)

##########################################################
# Slicing the model object
# ^^^^^^^^^^^^^^^^^^^^^^^^
# Although the model is fit to all values of reg_lambda specified by a regularization
# path, often we are only interested in further analysis for a particular value of
# ``reg_lambda``. We can easily do this by slicing the object.
#
# For instance ``model[0]`` returns an object identical to model but with ``.fit_``
# as a dictionary corresponding to the estimated coefficients for ``reg_lambda[0]``.

##########################################################
# Visualize the fit coefficients
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# The estimated coefficients are stored in an instance variable called ``.fit_``
# which is a list of dictionaries. Each dictionary corresponds to a
# particular ``reg_lambda``

##########################################################

fit_param = glm_poisson[-1].fit_
plt.plot(beta[:], 'bo', label ='true')
plt.plot(fit_param['beta'][:], 'ro', label='estimated')
plt.xlabel('samples')
plt.ylabel('outputs')
plt.legend(bbox_to_anchor=(0., 1.02, 1., .102), loc=1,
           ncol=2, borderaxespad=0.)
plt.show()

##########################################################
# Make predictions based on fit model
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# The ``predict()`` method takes two parameters: a numpy 2d array of independent
# variables and a dictionary of fit parameters. It returns a vector of
# predicted targets.

##########################################################

# Predict targets from test set
yrhat = glm_poisson[-1].predict(scaler.transform(Xr))
ythat = glm_poisson[-1].predict(scaler.transform(Xt))

plt.plot(yt[:100], label='true')
plt.plot(ythat[:100], 'r', label='predicted')
plt.xlabel('samples')
plt.ylabel('true and predicted outputs')
plt.legend(bbox_to_anchor=(0., 1.02, 1., .102), loc=1,
           ncol=2, borderaxespad=0.)
plt.show()

##########################################################
# Goodness of fit
# ^^^^^^^^^^^^^^^
# The GLM class provides two metrics to evaluate the goodness of fit: ``deviance``
# and ``pseudo_R2``. Both these metrics are implemented in the ``score()`` method.

##########################################################

# Compute model deviance
Dr = glm_poisson[-1].score(Xr, yr)
Dt = glm_poisson[-1].score(Xt, yt)
print('Dr = %f' % Dr, 'Dt = %f' % Dt)

# Compute pseudo_R2s
glm_poisson.score_metric = 'pseudo_R2'
R2r = glm_poisson[-1].score(Xr, yr)
R2t = glm_poisson[-1].score(Xt, yt)
print('  R2r =  %f' % R2r, ' R2r = %f' % R2t)
