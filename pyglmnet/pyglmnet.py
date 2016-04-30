import numpy as np
from scipy.special import expit
from scipy.stats import zscore


def softmax(w):
    """
    Softmax function of given array of number w
    """
    w = np.array(w)
    maxes = np.amax(w, axis=1)
    maxes = maxes.reshape(maxes.shape[0], 1)
    e = np.exp(w - maxes)
    dist = e / np.sum(e, axis=1, keepdims=True)
    return dist


class GLM:
    """Generalized Linear Model (GLM)

    This is class implements  elastic-net regularized generalized linear models.
    The core algorithm is defined in the ariticle

    Parameters
    ----------
    distr: str, distribution family in this following
        'poisson' or 'normal' or 'binomial' or 'multinomial'
        default: 'poisson'
    alpha: float, the weighting between L1 and L2 norm in penalty term
        loss function i.e.
            P(beta) = 0.5*(1-alpha)*|beta|_2^2 + alpha*|beta|_1
        default: 0.5
    reg_lambda: array or list, array of regularized parameters of penalty term i.e.
            (1/2*N) sum(y - beta*X) + lambda*P
        where lambda is number in reg_lambda list
        default: np.logspace(np.log(0.5), np.log(0.01), 10, base=np.exp(1))
    learning_rate: float, learning rate for gradient descent,
        default: 1e-4
    max_iter: int, maximum iteration for the model, default: 100
    threshold: float, threshold for convergence. Optimization loop will stop
        below setting threshold, default: 1e-3
    verbose: boolean, if True it will print output while iterating

    Reference
    ---------
    Friedman, Hastie, Tibshirani (2010). Regularization Paths for Generalized Linear
        Models via Coordinate Descent, J Statistical Software.
        https://core.ac.uk/download/files/153/6287975.pdf
    """

    def __init__(self, distr='poisson', alpha=0.05,
                 reg_lambda=np.logspace(np.log(0.5), np.log(0.01), 10, base=np.exp(1)),
                 learning_rate=1e-4, max_iter=100, verbose=False):
        self.distr = distr
        self.alpha = alpha
        self.reg_lambda = reg_lambda
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.fit_params = None
        self.verbose = False
        self.threshold = 1e-3

    def qu(self, z):
        """The non-linearity."""
        eps = np.spacing(1)
        qu = dict(poisson=np.log(1 + eps + np.exp(z)),
                  normal=z, binomial=expit(z),
                  multinomial=softmax(z))
        return qu[self.distr]

    def lmb(self, beta0, beta, X):
        """Conditional intensity function."""
        z = beta0 + np.dot(X, beta)
        l = self.qu(z)
        return l

    def logL(self, beta0, beta, X, y):
        """The log likelihood."""
        l = self.lmb(beta0, beta, X)
        if(self.distr == 'poisson'):
            logL = np.sum(y * np.log(l) - l)
        elif(self.distr == 'normal'):
            logL = -0.5 * np.sum((y - l)**2)
        elif(self.distr == 'binomial'):
            # analytical formula
            #logL = np.sum(y*np.log(l) + (1-y)*np.log(1-l))

            # this prevents underflow
            z = beta0 + np.dot(X, beta)
            logL = np.sum(y * z - np.log(1 + np.exp(z)))
        elif(self.distr == 'multinomial'):
            logL = -np.sum(y * np.log(l))
        return logL

    def penalty(self, beta):
        """The penalty."""
        alpha = self.alpha
        P = 0.5 * (1 - alpha) * np.linalg.norm(beta, 2) + \
            alpha * np.linalg.norm(beta, 1)
        return P

    def loss(self, beta0, beta, reg_lambda, X, y):
        """Define the objective function for elastic net."""
        alpha = self.alpha
        L = self.logL(beta0, beta, X, y)
        P = self.penalty(beta)
        J = -L + reg_lambda * P
        return J

    def L2loss(self, beta0, beta, reg_lambda, X, y):
        """Quadratic loss."""
        alpha = self.alpha
        L = self.logL(beta0, beta, X, y)
        P = 0.5 * (1 - alpha) * np.linalg.norm(beta, 2)
        J = -L + reg_lambda * P
        return J

    def prox(self, X, l):
        """Proximal operator."""
        # sx = [0. if np.abs(y) <= l else np.sign(y)*np.abs(abs(y)-l) for y in x]
        # return np.array(sx).reshape(x.shape)
        return np.sign(X) * (np.abs(X) - l) * (np.abs(X) > l)

    def grad_L2loss(self, beta0, beta, reg_lambda, X, y):
        """The gradient."""
        alpha = self.alpha
        z = beta0 + np.dot(X, beta)
        s = expit(z)

        if self.distr == 'poisson':
            q = self.qu(z)
            grad_beta0 = np.sum(s) - np.sum(y * s / q)
            grad_beta = np.transpose(np.dot(np.transpose(s), X) -
                                     np.dot(np.transpose(y * s / q), X)) + \
                reg_lambda * (1 - alpha) * beta
            # + reg_lambda*alpha*np.sign(beta)

        elif self.distr == 'normal':
            grad_beta0 = -np.sum(y - z)
            grad_beta = -np.transpose(np.dot(np.transpose(y - z), X)) \
                + reg_lambda * (1 - alpha) * beta
            # + reg_lambda*alpha*np.sign(beta)

        elif self.distr == 'binomial':
            grad_beta0 = np.sum(s - y)
            grad_beta = np.transpose(np.dot(np.transpose(s - y), X)) \
                + reg_lambda * (1 - alpha) * beta
            # + reg_lambda*alpha*np.sign(beta)
        elif self.distr == 'multinomial':
            # this assumes that y is already as a one-hot encoding
            pred = self.qu(z)
            grad_beta0 = -np.sum(y - pred)
            grad_beta = -np.transpose(np.dot(np.transpose(y - pred), X)) \
                + reg_lambda * (1 - alpha) * beta

        return grad_beta0, grad_beta

    def fit(self, X, y):
        """The fit function."""
        # Implements batch gradient descent (i.e. vanilla gradient descent by
        # computing gradient over entire training set)


        # Dataset shape
        p = X.shape[1]

        if len(y.shape) == 1:
            # convert to 1-hot encoding
            y_bk = y
            y = np.zeros([X.shape[0], y.max() + 1])
            for i in range(X.shape[0]):
                y[i, y_bk[i]] = 1.

        # number of predictions
        k = y.shape[1] if self.distr == 'multinomial' else 1

        # Initialize parameters
        beta0_hat = np.random.normal(0.0, 1.0, k)
        beta_hat = np.random.normal(0.0, 1.0, [p, k])
        fit_params = []

        # Outer loop with descending lambda
        if self.verbose is True:
            print('----------------------------------------')
            print('Looping through the regularization path')
            print('----------------------------------------')
        for l, rl in enumerate(self.reg_lambda):
            fit_params.append({'beta0': beta0_hat, 'beta': beta_hat})
            if self.verbose is True:
                print('Lambda: %6.4f') % rl

            # Warm initialize parameters
            if l == 0:
                fit_params[-1]['beta0'] = beta0_hat
                fit_params[-1]['beta'] = beta_hat
            else:
                fit_params[-1]['beta0'] = fit_params[-2]['beta0']
                fit_params[-1]['beta'] = fit_params[-2]['beta']

            # Iterate until convergence
            no_convergence = 1
            threshold = self.threshold
            alpha = self.alpha

            t = 0

            # Initialize parameters
            beta = np.zeros([p + 1, k])
            beta[0] = fit_params[-1]['beta0']
            beta[1:] = fit_params[-1]['beta']

            g = np.zeros([p + 1, k])
            # Initialize cost
            L = []
            DL = []

            while(no_convergence and t < self.max_iter):

                # Calculate gradient
                grad_beta0, grad_beta = self.grad_L2loss(
                    beta[0], beta[1:], rl, X, y)
                g[0] = grad_beta0
                g[1:] = grad_beta

                # Update time step
                t = t + 1

                # Update parameters
                beta = beta - self.learning_rate * g

                # Apply proximal operator for L1-regularization
                beta[1:] = self.prox(beta[1:], rl * alpha)

                # Calculate loss and convergence criteria
                L.append(self.loss(beta[0], beta[1:], rl, X, y))

                # Delta loss and convergence criterion
                if t > 1:
                    DL.append(L[-1] - L[-2])
                    if np.abs(DL[-1] / L[-1]) < threshold:
                        no_convergence = 0
                        if self.verbose is True:
                            print('    Converged. Loss function: {0:.2f}').format(
                                L[-1])
                            print('    dL/L: {0:.6f}\n').format(DL[-1] / L[-1])

            # Store the parameters after convergence
            fit_params[-1]['beta0'] = beta[0]
            fit_params[-1]['beta'] = beta[1:]

        self.fit_params = fit_params
        return self

    def predict(self, X, fit_param):
        """Define the predict function."""
        yhat = self.lmb(fit_param['beta0'], fit_param['beta'], zscore(X))
        return yhat

    def pseudo_R2(self, y, yhat, ynull):
        """Define the pseudo-R2 function."""
        eps = np.spacing(1)
        if self.distr == 'poisson':
            # Log likelihood of model under consideration
            L1 = np.sum(y * np.log(eps + yhat) - yhat)

            # Log likelihood of homogeneous model
            L0 = np.sum(y * np.log(eps + ynull) - ynull)

            # Log likelihood of saturated model
            LS = np.sum(y * np.log(eps + y) - y)
            R2 = 1 - (LS - L1) / (LS - L0)

        elif self.distr == 'binomial':
            # Log likelihood of model under consideration
            L1 = 2 * len(y) * np.sum(y * np.log((yhat == 0) + yhat) / np.mean(yhat) +
                                     (1 - y) * np.log((yhat == 1) + 1 - yhat) / (1 - np.mean(yhat)))

            # Log likelihood of homogeneous model
            L0 = 2 * len(y) * np.sum(y * np.log((ynull == 0) + ynull) / np.mean(yhat) +
                                     (1 - y) * np.log((ynull == 1) + 1 - ynull) / (1 - np.mean(yhat)))
            R2 = 1 - L1 / L0

        elif self.distr == 'normal':
            R2 = 1 - np.sum((y - yhat)**2) / np.sum((y - ynull)**2)

        return R2

    def deviance(self, y, yhat):
        """The deviance function."""
        eps = np.spacing(1)
        # L1 = Log likelihood of model under consideration
        # LS = Log likelihood of saturated model
        if self.distr == 'poisson':
            L1 = np.sum(y * np.log(eps + yhat) - yhat)
            LS = np.sum(y * np.log(eps + y) - y)

        elif self.distr == 'binomial':
            L1 = 2 * len(y) * np.sum(y * np.log((yhat == 0) + yhat) / np.mean(yhat) +
                                     (1 - y) * np.log((yhat == 1) + 1 - yhat) / (1 - np.mean(yhat)))
            LS = 0

        elif self.distr == 'normal':
            L1 = -np.sum((y - yhat)**2)
            LS = 0

        D = -2 * (L1 - LS)
        return D

    def simulate(self, beta0, beta, X):
        """Simulate data."""
        if self.distr == 'poisson':
            y = np.random.poisson(self.lmb(beta0, beta, zscore(X)))
        if self.distr == 'normal':
            y = np.random.normal(self.lmb(beta0, beta, zscore(X)))
        if self.distr == 'binomial':
            y = np.random.binomial(1, self.lmb(beta0, beta, zscore(X)))
        return y
