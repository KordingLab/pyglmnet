"""Python implementation of elastic-net regularized GLMs."""

from copy import deepcopy

import numpy as np
from scipy.special import expit
from .utils import logger, set_log_level
from . import metrics


def _lmb(distr, beta0, beta, X, eta):
    """Conditional intensity function."""
    z = beta0 + np.dot(X, beta)
    return _qu(distr, z, eta)


def _qu(distr, z, eta):
    """The non-linearity."""
    if distr == 'softplus':
        qu = np.log1p(np.exp(z))
    elif distr == 'poisson':
        qu = deepcopy(z)
        slope = np.exp(eta)
        intercept = (1 - eta) * slope
        qu[z > eta] = z[z > eta] * slope + intercept
        qu[z <= eta] = np.exp(z[z <= eta])
    elif distr == 'gaussian':
        qu = z
    elif distr == 'binomial':
        qu = expit(z)
    return qu


def _logL(distr, beta0, beta, X, y, eta):
    """The log likelihood."""
    n_samples = np.float(X.shape[0])
    z = beta0 + np.dot(X, beta)
    l = _qu(distr, z, eta)
    if distr == 'softplus':
        logL = 1. / n_samples * np.sum(y * np.log(l) - l)
    elif distr == 'poisson':
        logL = 1. / n_samples * np.sum(y * np.log(l) - l)
    elif distr == 'gaussian':
        logL = -0.5 * 1. / n_samples * np.sum((y - l)**2)
    elif distr == 'binomial':
        # analytical formula
        # logL = np.sum(y*np.log(l) + (1-y)*np.log(1-l))

        # but this prevents underflow
        z = beta0 + np.dot(X, beta)
        logL = 1. / n_samples * np.sum(y * z - np.log(1 + np.exp(z)))
    return logL


def _penalty(alpha, beta, Tau, group):
    """The penalty."""
    # Combine L1 and L2 penalty terms
    P = 0.5 * (1 - alpha) * _L2penalty(beta, Tau) + \
        alpha * _L1penalty(beta, group)
    return P


def _L2penalty(beta, Tau):
    """The L2 penalty."""
    # Compute the L2 penalty
    if Tau is None:
        # Ridge=like penalty
        L2penalty = np.linalg.norm(beta, 2) ** 2
    else:
        # Tikhonov penalty
        if (Tau.shape[0] != beta.shape[0] or
           Tau.shape[1] != beta.shape[0]):
            raise ValueError('Tau should be (n_features x n_features)')
        else:
            L2penalty = np.linalg.norm(np.dot(Tau, beta), 2) ** 2
    return L2penalty


def _L1penalty(beta, group=None):
    """The L1 penalty."""
    # Compute the L1 penalty
    if group is None:
        # Lasso-like penalty
        L1penalty = np.linalg.norm(beta, 1)
    else:
        # Group sparsity case: apply group sparsity operator
        group_ids = np.unique(group)
        L1penalty = 0.0
        for group_id in group_ids:
            if group_id != 0:
                L1penalty += \
                    np.linalg.norm(beta[group == group_id], 2)
        L1penalty += np.linalg.norm(beta[group == 0], 1)
    return L1penalty


def _loss(distr, alpha, Tau, reg_lambda, X, y, eta, group, beta):
    """Define the objective function for elastic net."""
    L = _logL(distr, beta[0], beta[1:], X, y, eta)
    P = _penalty(alpha, beta[1:], Tau, group)
    J = -L + reg_lambda * P
    return J


def _L2loss(distr, alpha, Tau, reg_lambda, X, y, eta, group, beta):
    """Define the objective function for elastic net."""
    L = _logL(distr, beta[0], beta[1:], X, y, eta)
    P = 0.5 * (1 - alpha) * _L2penalty(beta[1:], Tau)
    J = -L + reg_lambda * P
    return J


def _grad_L2loss(distr, alpha, Tau, reg_lambda, X, y, eta, beta):
    """The gradient."""

    n_samples = np.float(X.shape[0])

    if Tau is None:
        Tau = np.eye(beta[1:].shape[0])
    InvCov = np.dot(Tau.T, Tau)

    z = beta[0] + np.dot(X, beta[1:])
    s = expit(z)

    if distr == 'softplus':
        q = _qu(distr, z, eta)
        grad_beta0 = 1. / n_samples * (np.sum(s) - np.sum(y * s / q))
        grad_beta = 1. / n_samples * \
            ((np.dot(s.T, X) - np.dot((y * s / q).T, X)).T) + \
            reg_lambda * (1 - alpha) * np.dot(InvCov, beta[1:])

    elif distr == 'poisson':
        q = _qu(distr, z, eta)
        grad_beta0 = np.sum(q[z <= eta] - y[z <= eta]) + \
            np.sum(1 - y[z > eta] / q[z > eta]) * \
            np.exp(eta)
        grad_beta0 *= 1. / n_samples

        grad_beta = np.zeros([X.shape[1], ])
        selector = np.where(z.ravel() <= eta)[0]
        grad_beta += np.transpose(np.dot((q[selector] - y[selector]).T,
                                         X[selector, :]))
        selector = np.where(z.ravel() > eta)[0]
        grad_beta += np.exp(eta) * \
            np.transpose(np.dot((1 - y[selector] / q[selector]).T,
                                X[selector, :]))
        grad_beta *= 1. / n_samples
        grad_beta += reg_lambda * (1 - alpha) * \
            np.dot(InvCov, beta[1:])

    elif distr == 'gaussian':
        grad_beta0 = 1. / n_samples * np.sum(z - y)
        grad_beta = 1. / n_samples * \
            np.transpose(np.dot(np.transpose(z - y), X)) \
            + reg_lambda * (1 - alpha) * \
            np.dot(InvCov, beta[1:])

    elif distr == 'binomial':
        grad_beta0 = 1. / n_samples * np.sum(s - y)
        grad_beta = 1. / n_samples * \
            np.transpose(np.dot(np.transpose(s - y), X)) \
            + reg_lambda * (1 - alpha) * \
            np.dot(InvCov, beta[1:])

    n_features = X.shape[1]
    g = np.zeros((n_features + 1, ))
    g[0] = grad_beta0
    g[1:] = grad_beta
    return g


class GLM(object):
    """Class for estimating regularized generalized linear models (GLM).
    The regularized GLM minimizes the penalized negative log likelihood:

    .. math::

        \min_{\\beta_0, \\beta} \\frac{1}{N}
        \sum_{i = 1}^N \mathcal{L} (y_i, \\beta_0 + \\beta^T x_i)
        + \lambda [ \\frac{1}{2}(1 - \\alpha) \mathcal{P}_2 +
                    \\alpha \mathcal{P}_1 ]

    where :math:`\mathcal{P}_2` and :math:`\mathcal{P}_1` are the generalized
    L2 (Tikhonov) and generalized L1 (Group Lasso) penalties, given by:

    .. math::

        \mathcal{P}_2 = \|\Gamma \\beta \|_2^2 \\
        \mathcal{P}_1 = \sum_g \|\\beta_{j,g}\|_2

    where :math:`\Gamma` is the Tikhonov matrix: a square factorization
    of the inverse covariance matrix and :math:`\\beta_{j,g}` is the
    :math:`j` th coefficient of group :math:`g`.

    The generalized L2 penalty defaults to the ridge penalty when
    :math:`\Gamma` is identity.

    The generalized L1 penalty defaults to the lasso penalty when each
    :math:`\\beta` belongs to its own group.

    Parameters
    ----------
    distr : str
        distribution family can be one of the following
        'gaussian' | 'binomial' | 'poisson' | 'softplus'
        default: 'poisson'.
    alpha : float
        the weighting between L1 penalty and L2 penalty term
        of the loss function.
        default: 0.5
    Tau : array | None
        the (n_features, n_features) Tikhonov matrix.
        default: None, in which case Tau is identity
        and the L2 penalty is ridge-like
    group : array | list | None
        the (n_features, )
        list or array of group identities for each parameter :math:`\\beta`.
        Each entry of the list/ array should contain an int from 1 to n_groups
        that specify group membership for each parameter
        (except :math:`\\beta_0`).
        If you do not want to specify a group for a specific parameter,
        set it to zero.
        default: None, in which case it defaults to L1 regularization
    reg_lambda : array | list | None
        array of regularized parameters :math:`\\lambda` of penalty term.
        default: None, a list of 10 floats spaced logarithmically (base e)
        between 0.5 and 0.01.
    solver : str
        optimization method, can be one of the following
        'batch-gradient' (vanilla batch gradient descent)
        'cdfast' (Newton coordinate gradient descent).
        default: 'batch-gradient'
    learning_rate : float
        learning rate for gradient descent.
        default: 2e-1
    max_iter : int
        maximum iterations for the model.
        default: 1000
    tol : float
        convergence threshold or stopping criteria.
        Optimization loop will stop below setting threshold.
        default: 1e-3
    eta : float
        a threshold parameter that linearizes the exp() function above eta.
        default: 2.0
    score_metric : str
        specifies the scoring metric.
        one of either 'deviance' or 'pseudo_R2'.
        default: 'deviance'
    random_state : int
        seed of the random number generator used to initialize the solution.
        default: 0
    verbose : boolean or int
        default: False

    Reference
    ---------
    Friedman, Hastie, Tibshirani (2010). Regularization Paths for Generalized
        Linear Models via Coordinate Descent, J Statistical Software.
        https://core.ac.uk/download/files/153/6287975.pdf

    Notes
    -----
    To select subset of fitted glm models, you can simply do:

    >>> glm = glm[1:3]
    >>> glm[2].predict(X_test)
    """

    def __init__(self, distr='poisson', alpha=0.5,
                 Tau=None, group=None,
                 reg_lambda=None,
                 solver='batch-gradient',
                 learning_rate=2e-1, max_iter=1000,
                 tol=1e-3, eta=2.0, score_metric='deviance',
                 random_state=0, verbose=False):

        if reg_lambda is None:
            reg_lambda = np.logspace(np.log(0.5), np.log(0.01), 10,
                                     base=np.exp(1))
        if not isinstance(reg_lambda, (list, np.ndarray)):
            reg_lambda = [reg_lambda]
        if not isinstance(max_iter, int):
            max_iter = int(max_iter)

        self.distr = distr
        self.alpha = alpha
        self.reg_lambda = reg_lambda
        self.Tau = Tau
        self.group = group
        self.solver = solver
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.fit_ = None
        self.ynull_ = None
        self.tol = tol
        self.eta = eta
        self.score_metric = score_metric
        self.random_state = random_state
        self.verbose = verbose
        set_log_level(verbose)

    def get_params(self, deep=False):
        """Return class attributes in a dictionary."""
        return dict(
            (
                ('distr', self.distr),
                ('alpha', self.alpha),
                ('Tau', self.Tau),
                ('group', self.group),
                ('reg_lambda', self.reg_lambda),
                ('learning_rate', self.learning_rate),
                ('max_iter', self.max_iter),
                ('tol', self.tol),
                ('eta', self.eta),
                ('score_metric', self.score_metric),
                ('random_state', self.random_state),
                ('verbose', self.verbose)
            )
        )

    def set_params(self, params):
        """Assign class attributes from a dictionary."""
        for key, value in params.iteritems():
            setattr(self, key, value)

    def __repr__(self):
        """Description of the object."""
        reg_lambda = self.reg_lambda
        s = '<\nDistribution | %s' % self.distr
        s += '\nalpha | %0.2f' % self.alpha
        s += '\nmax_iter | %0.2f' % self.max_iter
        if len(reg_lambda) > 1:
            s += ('\nlambda: %0.2f to %0.2f\n>'
                  % (reg_lambda[0], reg_lambda[-1]))
        else:
            s += '\nlambda: %0.2f\n>' % reg_lambda[0]
        return s

    def __getitem__(self, key):
        """Return a GLM object with a subset of fitted lambdas."""
        glm = deepcopy(self)
        if self.fit_ is None:
            raise ValueError('Cannot slice object if the lambdas have'
                             ' not been fit.')
        if not isinstance(key, (slice, int)):
            raise IndexError('Invalid slice for GLM object')
        glm.fit_ = glm.fit_[key]
        glm.reg_lambda = glm.reg_lambda[key]
        return glm

    def copy(self):
        """Return a copy of the object.

        Parameters
        ----------
        none:

        Returns
        -------
        self: instance of GLM
            A copy of the GLM instance.
        """
        return deepcopy(self)

    def _prox(self, beta, thresh):
        """Proximal operator."""
        if self.group is None:
            # The default case: soft thresholding
            return np.sign(beta) * (np.abs(beta) - thresh) * \
                (np.abs(beta) > thresh)
        else:
            # Group sparsity case: apply group sparsity operator
            group_ids = np.unique(self.group)
            group_norms = np.abs(beta)

            for group_id in group_ids:
                if group_id != 0:
                    group_norms[self.group == group_id] = \
                        np.linalg.norm(beta[self.group == group_id], 2)

            nzero_norms = group_norms > 0.0
            over_thresh = group_norms > thresh
            idxs_to_update = nzero_norms & over_thresh

            result = beta
            result[idxs_to_update] = (beta[idxs_to_update] -
                                      thresh * beta[idxs_to_update] /
                                      group_norms[idxs_to_update])

            return result

    def _gradhess_logloss_1d(self, xk, y, z):
        """
        Compute gradient (1st derivative)
        and Hessian (2nd derivative)
        of log likelihood for a single coordinate.

        Parameters
        ----------
        xk: float
            n_samples x 1
        y: float
            n_samples x 1
        z: float
            n_samples x 1

        Returns
        -------
        gk: float:
            gradient
        hk: float:
            hessian
        """
        n_samples = xk.shape[0]

        if self.distr == 'softplus':
            mu = _qu(self.distr, z, self.eta)
            s = expit(z)
            gk = np.sum(s * xk) - np.sum(y * s / mu * xk)

            grad_s = s * (1 - s)
            grad_s_by_mu = grad_s / mu - s / (mu ** 2)
            hk = np.sum(grad_s * xk ** 2) - np.sum(y * grad_s_by_mu * xk ** 2)

        elif self.distr == 'poisson':
            mu = _qu(self.distr, z, self.eta)
            s = expit(z)
            gk = np.sum((mu[z <= self.eta] - y[z <= self.eta]) *
                        xk[z <= self.eta]) + \
                np.exp(self.eta) * \
                np.sum((1 - y[z > self.eta] / mu[z > self.eta]) *
                       xk[z > self.eta])
            hk = np.sum(mu[z <= self.eta] * xk[z <= self.eta] ** 2) + \
                np.exp(self.eta) ** 2 * \
                np.sum(y[z > self.eta] / (mu[z > self.eta] ** 2) *
                       (xk[z > self.eta] ** 2))

        elif self.distr == 'gaussian':
            gk = np.sum((z - y) * xk)
            hk = np.sum(xk * xk)

        elif self.distr == 'binomial':
            mu = _qu(self.distr, z, self.eta)
            gk = np.sum((mu - y) * xk)
            hk = np.sum(mu * (1.0 - mu) * xk * xk)

        return 1. / n_samples * gk, 1. / n_samples * hk

    def _cdfast(self, X, y, z, ActiveSet, beta, rl):
        """
        Performs one cycle of Newton updates for all coordinates

        Parameters
        ----------
        X : array
            n_samples x n_features
            The input data
        y : array
            Labels to the data
            n_samples x 1
        z:  array
            n_samples x 1
            beta[0] + X * beta[1:]
        ActiveSet: array
            n_features + 1 x 1
            Active set storing which betas are non-zero
        beta: array
            n_features + 1 x 1
            Parameters to be updated
        rl: float
            Regularization lambda

        Returns
        -------
        beta: array
            (n_features + 1) x 1
            Updated parameters
        z: array
            beta[0] + X * beta[1:]
            (n_features + 1) x 1
        """
        n_samples = X.shape[0]
        n_features = X.shape[1]
        reg_scale = rl * (1 - self.alpha)

        for k in range(0, n_features + 1):
            # Only update parameters in active set
            if ActiveSet[k] != 0:
                if k > 0:
                    xk = X[:, k - 1]
                else:
                    xk = np.ones((n_samples, ))

                # Calculate grad and hess of log likelihood term
                gk, hk = self._gradhess_logloss_1d(xk, y, z)

                # Add grad and hess of regularization term
                if self.Tau is None:
                    gk_reg = beta[k]
                    hk_reg = 1.0
                else:
                    InvCov = np.dot(self.Tau.T, self.Tau)
                    gk_reg = np.sum(InvCov[k - 1, :] * beta[1:])
                    hk_reg = InvCov[k - 1, k - 1]
                gk += np.ravel([reg_scale * gk_reg if k > 0 else 0.0])
                hk += np.ravel([reg_scale * hk_reg if k > 0 else 0.0])

                # Update parameters, z
                update = 1. / hk * gk
                beta[k], z = beta[k] - update, z - update * xk
        return beta, z

    def fit(self, X, y):
        """The fit function.

        Parameters
        ----------
        X : array
            The input data of shape (n_samples, n_features)

        y : array
            The target data

        Returns
        -------
        self : instance of GLM
            The fitted model.
        """

        np.random.RandomState(self.random_state)

        # checks for group
        if self.group is not None:
            self.group = np.array(self.group)
            self.group.dtype = np.int64
            # shape check
            if self.group.shape[0] != X.shape[1]:
                raise ValueError('group should be (n_features,)')
            # int check
            if not np.all([isinstance(g, np.int64) for g in self.group]):
                raise ValueError('all entries of group should be integers')

        # type check for data matrix
        if not isinstance(X, np.ndarray):
            raise ValueError('Input data should be of type ndarray (got %s).'
                             % type(X))

        n_features = X.shape[1]

        # Initialize parameters
        beta0_hat = 1 / (n_features + 1) * \
            np.random.normal(0.0, 1.0, 1)
        beta_hat = 1 / (n_features + 1) * \
            np.random.normal(0.0, 1.0, (n_features, ))
        fit_params = list()

        logger.info('Looping through the regularization path')
        for l, rl in enumerate(self.reg_lambda):
            fit_params.append({'beta0': beta0_hat, 'beta': beta_hat})
            logger.info('Lambda: %6.4f' % rl)

            # Warm initialize parameters
            if l == 0:
                fit_params[-1]['beta0'] = beta0_hat
                fit_params[-1]['beta'] = beta_hat
            else:
                fit_params[-1]['beta0'] = fit_params[-2]['beta0']
                fit_params[-1]['beta'] = fit_params[-2]['beta']

            tol = self.tol
            alpha = self.alpha

            # Temporary parameters to update
            beta = np.zeros((n_features + 1,))
            beta[0] = fit_params[-1]['beta0']
            beta[1:] = fit_params[-1]['beta']

            if self.solver == 'batch-gradient':
                g = np.zeros((n_features + 1, ))
            elif self.solver == 'cdfast':
                ActiveSet = np.ones(n_features + 1)     # init active set
                z = beta[0] + np.dot(X, beta[1:])       # cache z

            # Initialize loss accumulators
            L, DL = list(), list()
            for t in range(0, self.max_iter):
                if self.solver == 'batch-gradient':
                    grad = _grad_L2loss(self.distr,
                                        self.alpha, self.Tau,
                                        rl, X, y, self.eta,
                                        beta)

                    beta = beta - self.learning_rate * grad
                elif self.solver == 'cdfast':
                    beta, z = self._cdfast(X, y, z, ActiveSet, beta, rl)

                # Apply proximal operator
                beta[1:] = self._prox(beta[1:], rl * alpha)

                # Update active set
                if self.solver == 'cdfast':
                    ActiveSet[np.where(beta[1:] == 0)[0] + 1] = 0

                # Compute and save loss
                L.append(_loss(self.distr, self.alpha, self.Tau, rl,
                               X, y, self.eta, self.group, beta))

                if t > 1:
                    DL.append(L[-1] - L[-2])
                    if np.abs(DL[-1] / L[-1]) < tol:
                        msg = ('\tConverged. Loss function:'
                               ' {0:.2f}').format(L[-1])
                        logger.info(msg)
                        msg = ('\tdL/L: {0:.6f}\n'.format(DL[-1] / L[-1]))
                        logger.info(msg)
                        break

            fit_params[-1]['beta0'] = beta[0]
            fit_params[-1]['beta'] = beta[1:]

        # Update the estimated variables
        self.fit_ = fit_params
        self.ynull_ = np.mean(y)

        # Return
        return self

    def predict(self, X):
        """Predict targets.

        Parameters
        ----------
        X : array
            Input data for prediction, of shape (n_samples, n_features)

        Returns
        -------
        yhat : array
            The predicted targets of shape ([n_lambda], n_samples)
            A 1D array if predicting on only
            one reg_lambda (compatible with scikit-learn API).
            Otherwise, returns a 2D array.
        """
        if not isinstance(X, np.ndarray):
            raise ValueError('Input data should be of type ndarray (got %s).'
                             % type(X))

        if isinstance(self.fit_, list):
            yhat = list()
            for fit in self.fit_:
                y_pred = _lmb(self.distr, fit['beta0'],
                              fit['beta'], X, self.eta)
                if self.distr == 'binomial':
                    yhat.append((y_pred > 0.5).astype(int))
                else:
                    yhat.append(y_pred)
        else:
            yhat = _lmb(self.distr, self.fit_['beta0'],
                        self.fit_['beta'], X, self.eta)
            if self.distr == 'binomial':
                yhat = (yhat > 0.5).astype(int)
        yhat = np.asarray(yhat)
        return yhat

    def predict_proba(self, X):
        """Predict class probability for binomial

        Parameters
        ----------
        X : array
            Input data for prediction, of shape (n_samples, n_features)

        Returns
        -------
        yhat : array
            The predicted targets of shape
            ([n_lambda], n_samples).
            A 2D array if predicting on only
            one lambda (compatible with scikit-learn API).
            Otherwise, returns a 3D array.

        Raises
        ------
        Works only for the binomial distribution.
        Raises error otherwise.

        """
        if self.distr != 'binomial':
            raise ValueError('This is only applicable for \
                              the binomial distribution.')

        if not isinstance(X, np.ndarray):
            raise ValueError('Input data should be of type ndarray (got %s).'
                             % type(X))

        if isinstance(self.fit_, list):
            yhat = list()
            for fit in self.fit_:
                yhat.append(_lmb(self.distr,
                            fit['beta0'], fit['beta'], X, self.eta))
        else:
            yhat = _lmb(self.distr,
                        self.fit_['beta0'], self.fit_['beta'], X, self.eta)
        yhat = np.asarray(yhat)
        return yhat

    def fit_predict(self, X, y):
        """Fit the model and predict on the same data.

        Parameters
        ----------
        X : array
            The input data to fit and predict,
            of shape (n_samples, n_features)


        Returns
        -------
        yhat : array
            The predicted targets of shape ([n_lambda], n_samples).
            A 1D array if predicting on only
            one lambda (compatible with scikit-learn API).
            Otherwise, returns a 2D array.
        """
        return self.fit(X, y).predict(X)

    def score(self, X, y):
        """Score the model.

        Parameters
        ----------
        X : array
            The input data whose prediction will be scored,
            of shape (n_samples, n_features).
        y : array
            The true targets against which to score the predicted targets,
            of shape (n_samples,).

        Returns
        -------
        score: array
            array when score is called by a list of estimators:
            :code:`glm.score()`
            singleton array when score is called by a sliced estimator:
            :code:`glm[0].score()`

        Examples
        --------
        Note that if you want compatibility with scikit-learn's
        :code:`pipeline()`, :code:`cross_val_score()`,
        or :code:`GridSearchCV()` then you should only pass sliced estimators:

            >>> from sklearn.grid_search import GridSearchCV
            >>> from sklearn.cross_validation import cross_val_score
            >>> grid = GridSearchCV(glm[0])
            >>> grid = cross_val_score(glm[0], X, y, cv=10)
        """

        if self.score_metric not in ['deviance', 'pseudo_R2', 'accuracy']:
            raise ValueError('score_metric has to be one of' +
                             ' deviance or pseudo_R2')

        # If the model has not been fit it cannot be scored
        if self.ynull_ is None:
            raise ValueError('Model must be fit before ' +
                             'prediction can be scored')

        # For f1 as well
        if self.score_metric in ['accuracy']:
            if self.distr not in ['binomial', 'multinomial']:
                raise ValueError(self.score_metric +
                                 ' is only defined for binomial ' +
                                 'or multinomial distributions')

        y = y.ravel()

        if self.distr == 'binomial' and self.score_metric != 'accuracy':
            yhat = self.predict_proba(X)
        else:
            yhat = self.predict(X)

        # Check whether we have a list of estimators or a single estimator
        if isinstance(self.fit_, dict):
            yhat = yhat[np.newaxis, ...]

        if self.score_metric == "deviance":
            return metrics.deviance(y, yhat, self.ynull_, self.distr)
        elif self.score_metric == "pseudo_R2":
            return metrics.pseudo_R2(X, y, yhat, self.ynull_, self.distr)
        if self.score_metric == "accuracy":
            return metrics.accuracy(y, yhat)

    def simulate(self, beta0, beta, X):
        """Simulate target data under a generative model.

        Parameters
        ----------
        X: array
            design matrix of shape (n_samples, n_features)
        beta0: float
            intercept coefficient
        beta: array
            coefficients of shape (n_features,)

        Returns
        -------
        y: array
            simulated target data of shape (n_samples, 1)
        """
        np.random.RandomState(self.random_state)
        if self.distr == 'softplus' or self.distr == 'poisson':
            y = np.random.poisson(_lmb(self.distr, beta0, beta, X, self.eta))
        if self.distr == 'gaussian':
            y = np.random.normal(_lmb(self.distr, beta0, beta, X, self.eta))
        if self.distr == 'binomial':
            y = np.random.binomial(1, _lmb(self.distr, beta0,
                                           beta, X, self.eta))
        return y
