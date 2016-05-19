# pyglmnet

[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat)](https://github.com/pavanramkumar/pyglmnet/blob/master/LICENSE) [![Travis](https://api.travis-ci.org/pavanramkumar/pyglmnet.png?branch=master "Travis")](https://travis-ci.org/pavanramkumar/pyglmnet)
[![Coverage Status](https://coveralls.io/repos/github/pavanramkumar/pyglmnet/badge.svg?branch=master)](https://coveralls.io/github/pavanramkumar/pyglmnet?branch=master)
[![Gitter](https://badges.gitter.im/pavanramkumar/pyglmnet.svg)](https://gitter.im/pavanramkumar/pyglmnet?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge)

Python implementation of elastic-net regularized generalized linear models.

I follow the same approach and notations as in
[Friedman, J., Hastie, T., & Tibshirani, R. (2010)](https://core.ac.uk/download/files/153/6287975.pdf)
and the accompanying widely popular [R package](https://web.stanford.edu/~hastie/glmnet/glmnet_alpha.html).

The key difference is that we use ordinary batch gradient descent instead of
co-ordinate descent, which is very fast for `N x p` of up to `10000 x 1000`.

You can find some resources [here](doc/resources.rst).


### Simulating data and fitting a GLM in 5 minutes

Clone the repository.

```bash
$ git clone http://github.com/pavanramkumar/pyglmnet
```

Install `pyglmnet` using `setup.py` as following

```bash
$ python setup.py develop install
```


### Getting Started

Here is an example on how to use `GLM` class.

```python
import numpy as np
import scipy.sparse as sps
from sklearn.preprocessing import StandardScaler
from pyglmnet import GLM

# create an instance of the GLM class
glm = GLM(distr='poisson', verbose=True, alpha=0.05)

n_samples, n_features = 10000, 100

# coefficients
beta0 = np.random.normal(0.0, 1.0, 1)
beta = sps.rand(n_features, 1, 0.1)
beta = np.array(beta.todense())

# training data
Xr = np.random.normal(0.0, 1.0, [n_samples, n_features])
yr = glm.simulate(beta0, beta, Xr)

# testing data
Xt = np.random.normal(0.0, 1.0, [n_samples, n_features])
yt = glm.simulate(beta0, beta, Xt)

# fit Generalized Linear Model
scaler = StandardScaler().fit(Xr)
glm.fit(scaler.transform(Xr), yr)

# we'll get .fit_params after .fit(), here we get one set of fit parameters
fit_param = glm[-1].fit_

# we can use fitted parameters to predict
yhat = glm.predict(scaler.transform(Xt))
```

[See the full example on how to use `pyglmnet`](http://pavanramkumar.github.io/pyglmnet/auto_examples/plot_poisson.html)


### Tutorial

Find more extensive tutorial on posing and fitting the GLM
[here](http://pavanramkumar.github.io/pyglmnet/auto_examples/plot_glmnet.html)


### Note

We don't use the canonical link function `exp()` for `'poisson'` targets.
Instead, we use the softplus function: `log(1+exp())` for numerical stability.
For the canonical poisson link function, use `'poissonexp'`

### To contribute

We welcome any pull requests.
- Fork this repository
- Develop and push to your branch
- Create new pull requests

You can run `nosetests tests` before for making pull requests
to ensure that the changes work. We are continuously adding tests with more coverage.

### Author

* [Pavan Ramkumar](http:/github.com/pavanramkumar)

### Contributors

* [Daniel Acuna](http:/github.com/daniel-acuna)
* [Titipat Achakulvisut](http:/github.com/titipata)
* [Hugo Fernandes](http:/github.com/hugoguh)
* [Mainak Jas](http:/github.com/jasmainak)

### License

MIT License Copyright (c) 2016 Pavan Ramkumar
