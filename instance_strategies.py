import math
import numpy as np
import sys
from collections import defaultdict
from sklearn import metrics
import scipy.sparse as ss

from sklearn.naive_bayes import GaussianNB

class RandomBootstrap(object):
    def __init__(self, seed):
        self.randS = RandomStrategy(seed)
        
    def bootstrap(self, pool, y=None, k=1):
        return self.randS.chooseNext(pool, k=k)

class BootstrapFromEach(object):
    def __init__(self, seed):
        self.randS = RandomStrategy(seed)
        
    def bootstrap(self, pool, y, k=1):
        data = defaultdict(lambda: [])
        for i in pool:
            data[y[i]].append(i)
        chosen = []
        num_classes = len(data.keys())
        # print k/num_classes, k, num_classes
        for label in data.keys():
            candidates = data[label]
            indices = self.randS.chooseNext(candidates, k=k/num_classes)
            chosen.extend(indices)
        return chosen


class BaseStrategy(object):
    
    def __init__(self, seed=0):
        self.randgen = np.random
        self.randgen.seed(seed)
        
    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        pass

class RandomStrategy(BaseStrategy):
        
    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        list_pool = list(pool)
        rand_indices = self.randgen.permutation(len(pool))
        return [list_pool[i] for i in rand_indices[:k]]

class UncStrategy(BaseStrategy):
    
    def __init__(self, seed=0, sub_pool = None):
        super(UncStrategy, self).__init__(seed=seed)
        self.sub_pool = sub_pool
    
    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        
        num_candidates = len(pool)
        
        if self.sub_pool is not None:
            num_candidates = self.sub_pool
        
        rand_indices = self.randgen.permutation(len(pool))        
        list_pool = list(pool)        
        candidates = [list_pool[i] for i in rand_indices[:num_candidates]]
        
        if ss.issparse(X):
            if not ss.isspmatrix_csr(X):
                X = X.tocsr()
        
        probs = model.predict_proba(X[candidates])        
        uncerts = np.min(probs, axis=1)        
        uis = np.argsort(uncerts)[::-1]
        chosen = [candidates[i] for i in uis[:k]]       
        return chosen

class QBCStrategy(BaseStrategy):
    
    def __init__(self, classifier, classifier_args, seed=0, sub_pool = None, num_committee = 4):
        super(QBCStrategy, self).__init__(seed=seed)
        self.sub_pool = sub_pool
        self.num_committee = num_committee
        self.classifier = classifier
        self.classifier_args = classifier_args
        
    
    def vote_entropy(self, sample):
        """ Computes vote entropy. """
        votes = defaultdict(lambda: 0.0)
        size = float(len(sample))

        for i in sample:
            votes[i] += 1.0

        out = 0
        for i in votes:
            aux = (float(votes[i]/size))
            out += ((aux*math.log(aux, 2))*-1.)

        return out
    
    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
         

        num_candidates = len(pool)
        
        if self.sub_pool is not None:
            num_candidates = self.sub_pool
        
        rand_indices = self.randgen.permutation(len(pool))        
        list_pool = list(pool)        
        candidates = [list_pool[i] for i in rand_indices[:num_candidates]]
        
        if ss.issparse(X):
            if not ss.isspmatrix_csr(X):
                X = X.tocsr()
        
        # Create bags
        
        comm_predictions = []
        
        for c in range(self.num_committee):
            r_inds = self.randgen.randint(0, len(current_train_indices), size=len(current_train_indices))
            bag = [current_train_indices[i] for i in r_inds]
            bag_y = [current_train_y[i] for i in r_inds]
            new_classifier = self.classifier(**self.classifier_args)
            new_classifier.fit(X[bag], bag_y)
            
            predictions = new_classifier.predict(X[candidates])
            
            comm_predictions.append(predictions)
        
        # Compute disagreement for com_predictions

        disagreements = []
        for i in range(len(comm_predictions[0])):
            aux_candidates = []
            for prediction in comm_predictions:
                aux_candidates.append(prediction[i])
            disagreement = self.vote_entropy(aux_candidates)
            disagreements.append(disagreement)
        
        dis = np.argsort(disagreements)[::-1]
        chosen = [candidates[i] for i in dis[:k]]
        
        return chosen

class LogGainStrategy(BaseStrategy):
    
    def __init__(self, classifier, classifier_args, seed = 0, sub_pool = None):
        super(LogGainStrategy, self).__init__(seed=seed)
        self.classifier = classifier
        self.sub_pool = sub_pool
        self.classifier_args = classifier_args
    
    def log_gain(self, probs, labels):
        lg = 0
        for i in xrange(len(probs)):
            lg -= np.log(probs[i][int(labels[i])])
        return lg
    
    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        
        num_candidates = len(pool)
        
        if self.sub_pool is not None:
            num_candidates = self.sub_pool
        
        list_pool = list(pool)
        
        
        #random candidates
        rand_indices = self.randgen.permutation(len(pool))                
        candidates = [list_pool[i] for i in rand_indices[:num_candidates]]
        
        if ss.issparse(X):
            if not ss.isspmatrix_csr(X):
                X = X.tocsr()
                        
        cand_probs = model.predict_proba(X[candidates])    
        
        utils = []
        
        for i in xrange(num_candidates):
            #assume binary
            new_train_inds = list(current_train_indices)
            new_train_inds.append(candidates[i])
            util = 0
            for c in [0, 1]:
                new_train_y = list(current_train_y)
                new_train_y.append(c)
                new_classifier = self.classifier(**self.classifier_args)
                new_classifier.fit(X[new_train_inds], new_train_y)
                new_probs = new_classifier.predict_proba(X[current_train_indices])
                util += cand_probs[i][c] * self.log_gain(new_probs, current_train_y)
            
            utils.append(util)
        
        uis = np.argsort(utils)
        
        
        chosen = [candidates[i] for i in uis[:k]]
        
        return chosen

class ErrorReductionStrategy(BaseStrategy):
    
    def __init__(self, classifier, classifier_args, seed = 0, sub_pool = None):
        super(ErrorReductionStrategy, self).__init__(seed=seed)
        self.classifier = classifier
        self.sub_pool = sub_pool
        self.classifier_args = classifier_args
    
    def log_loss(self, probs):
        ll = 0

        for i in xrange(len(probs)):
            for prob in probs[i]:
                ll -= (prob*np.log(prob))

        return ll/(len(probs)*1.)
    
    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        
        num_candidates = len(pool)
        
        if self.sub_pool is not None:
            num_candidates = self.sub_pool
        
        list_pool = list(pool) #X[list_pool] = Unlabeled data = U = p
        
        
        #random candidates
        rand_indices = self.randgen.permutation(len(pool))                
        candidates = [list_pool[i] for i in rand_indices[:num_candidates]]
        
        if ss.issparse(X):
            if not ss.isspmatrix_csr(X):
                X = X.tocsr()
                        
        cand_probs = model.predict_proba(X[candidates])    
        
        utils = []
        
        for i in xrange(num_candidates):
            #assume binary
            new_train_inds = list(current_train_indices)
            new_train_inds.append(candidates[i])
            util = 0
            for c in [0, 1]:
                new_train_y = list(current_train_y)
                new_train_y.append(c)
                new_classifier = self.classifier(**self.classifier_args)
                new_classifier.fit(X[new_train_inds], new_train_y)
                new_probs = new_classifier.predict_proba(X[candidates]) #X[current_train_indices] = labeled = L
                util += cand_probs[i][c] * self.log_loss(new_probs)
            
            utils.append(util)
        
        uis = np.argsort(utils)
        
        
        chosen = [candidates[i] for i in uis[:k]]
        
        return chosen


class RotateStrategy(BaseStrategy):
    
    def __init__(self, strategies):
        super(RotateStrategy, self).__init__(seed=0)
        self.strategies = strategies
        self.counter = -1
    
    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        self.counter = (self.counter+1) % len(self.strategies)
        return self.strategies[self.counter].chooseNext(pool, X, model, k=k, current_train_indices = current_train_indices, current_train_y = current_train_y)
                

class Strategy1(BaseStrategy):
    
    def __init__(self, classifier, classifier_args, seed = 0, sub_pool = None, X_test = None, y_test = None, y_pool = None, option = 'log'):
        super(Strategy1, self).__init__(seed=seed)
        self.classifier = classifier
        self.sub_pool = sub_pool
        self.classifier_args = classifier_args
        self.X_test = X_test
        self.y_test = y_test
        self.y_pool = y_pool
        self.option = 'log'
        if option == 'accu':
            self.option = 'accu'
        elif option == 'auc':
            self.option = 'auc'

    
    def log_gain(self, probs, labels):
        lg = 0
        for i in xrange(len(probs)):
            lg += np.log(probs[i][int(labels[i])])
        return lg


    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        

        # print 'choosing'

        num_candidates = len(pool)
        
        if self.sub_pool is not None and len(pool) > self.sub_pool:
            num_candidates = self.sub_pool
        
        list_pool = list(pool)
        
        
        #random candidates
        rand_indices = self.randgen.permutation(len(pool))                
        candidates = [list_pool[i] for i in rand_indices[:num_candidates]]
        
        if ss.issparse(X):
            if not ss.isspmatrix_csr(X):
                X = X.tocsr()
                        
        utils = []
        
        for i in xrange(num_candidates):
            
            new_train_inds = list(current_train_indices)
            new_train_inds.append(candidates[i])
            
            
            new_train_y = list(current_train_y)
            new_train_y.append(self.y_pool[candidates[i]]) # check this # CHEATING 1

            util = -np.inf

            if len(set(new_train_y)) > 1:
                new_classifier = self.classifier(**self.classifier_args)
                new_classifier.fit(X[new_train_inds], new_train_y)

                if (self.classifier) == type(GaussianNB()):
                    new_probs = new_classifier.predict_proba(self.X_test.toarray())
                else:
                    new_probs = new_classifier.predict_proba(self.X_test)

                # compute utility # CHEATING 2
                if self.option == 'log':
                    #LOGGAIN on test
                    # new_probs = new_classifier.predict_proba(self.X_test)
                    util = self.log_gain(new_probs, self.y_test)

                elif self.option == 'auc':
                # OR AUC on the test
                    auc = metrics.roc_auc_score(self.y_test, new_probs[:,1])
                    util = auc
                    # print len(new_probs[:,1])
                    # print util

                elif self.option == 'accu':
                # OR accuracy on the test
                    pred_y = model.classes_[np.argmax(new_probs, axis=1)]
                    
                    accu = metrics.accuracy_score(self.y_test, pred_y)
                    util = accu
            
            utils.append(util)
        # print

        # print utils
        uis = np.argsort(utils)
        uis = uis[::-1]

        chosen = [candidates[i] for i in uis[:k]]
        # print
        # print self.X_test.shape[0], len(self.y_test)

        # sys.exit()
        
        # print 'chosen'

        return chosen

class Strategy2(BaseStrategy):
    
    def __init__(self, classifier, classifier_args, seed = 0, sub_pool = None, X_test = None, y_test = None, y_pool = None, option = 'log'):
        super(Strategy2, self).__init__(seed=seed)
        self.classifier = classifier
        self.sub_pool = sub_pool
        self.classifier_args = classifier_args
        self.X_test = X_test
        self.y_test = y_test
        self.y_pool = y_pool
        self.option = 'log'
        if option == 'accu':
            self.option = 'accu'
        elif option == 'auc':
            self.option = 'auc'
    
    def log_gain(self, probs, labels):
        lg = 0
        for i in xrange(len(probs)):
            lg += np.log(probs[i][int(labels[i])])
        return lg


    def chooseNext(self, pool, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        num_candidates = len(current_train_indices)
        
        if self.sub_pool is not None and num_candidates > self.sub_pool:
            num_candidates = self.sub_pool
        
        
        #random indices
        rand_indices = self.randgen.permutation(len(current_train_indices))
        
        
        if ss.issparse(X):
            if not ss.isspmatrix_csr(X):
                X = X.tocsr()
                        
        utils = []
        
        for i in rand_indices[:num_candidates]:
            
            new_train_inds = list(current_train_indices)
            del new_train_inds[i]
            
            new_train_y = list(current_train_y)
            del new_train_y[i]

            util = -np.inf
            # print set(new_train_y)
            if len(set(new_train_y)) > 1:
                new_classifier = self.classifier(**self.classifier_args)
                new_classifier.fit(X[new_train_inds], new_train_y)

                if (self.classifier) == type(GaussianNB()):
                    new_probs = new_classifier.predict_proba(self.X_test.toarray())
                else:
                    new_probs = new_classifier.predict_proba(self.X_test)

                # compute utility # CHEATING 2
                if self.option == 'log':
                    #LOGGAIN on test
                    # new_probs = new_classifier.predict_proba(self.X_test)
                    util = self.log_gain(new_probs, self.y_test)

                elif self.option == 'auc':
                # OR AUC on the test
                    auc = metrics.roc_auc_score(self.y_test, new_probs[:,1])
                    util = auc
                elif self.option == 'accu':
                # OR accuracy on the test
                    pred_y = model.classes_[np.argmax(new_probs, axis=1)]
                    
                    accu = metrics.accuracy_score(self.y_test, pred_y)
                    util = accu
            
            utils.append(util)
        # print
        uis = np.argsort(utils)
        uis = uis[::-1]

        chosen = [current_train_indices[rand_indices[i]] for i in uis[:k]]

        return chosen


"""
It takes the result of one strategy and tries to improve it, by replacing elements from the output by other in pool.
Uses accuracy, AUC or log gain to compare results
"""
def makeItBetter(X, y, X_test, y_test, current_train_indices, pool, number_trials, classifier, alpha, option='auc', seed=42):
    
    randgen = np.random
    randgen.seed(seed)
    comp = len(current_train_indices)
    comp2 = len(pool)

    new_classifier = classifier(**alpha)

    # Calculating accuracy, AUC or log gain of the giving current_train_indices
    previous_util = -np.inf

    if len(set(y[current_train_indices])) > 1:
        new_classifier.fit(X[current_train_indices], y[current_train_indices])

        if (classifier) == type(GaussianNB()):
                new_probs = new_classifier.predict_proba(X_test.toarray())
        else:
            new_probs = new_classifier.predict_proba(X_test)

        if option == 'log':
            previous_util = Strategy2.log_gain(new_probs, y_test)

        elif option == 'auc':
            auc = metrics.roc_auc_score(y_test, new_probs[:,1])
            previous_util = auc
        elif option == 'accu':
            pred_y = model.classes_[np.argmax(new_probs, axis=1)]
                    
            accu = metrics.accuracy_score(y_test, pred_y)
            previous_util = accu

    # Randomly replace values from training set by random elements from pool
    # Process is repeated number_trials times
    for i in range(number_trials):

        rand_indices = randgen.permutation(len(current_train_indices))
        rand_pool = randgen.permutation(len(pool))

        new_train_inds = list(current_train_indices)
        new_pool = list(pool)

        # Replacing values
        elem = new_pool[rand_pool[0]]
        del new_pool[rand_pool[0]]

        new_pool.append(new_train_inds[rand_indices[0]])
        del new_train_inds[rand_indices[0]]
        new_train_inds.append(elem)
        new_pool = set(new_pool)

        util = -np.inf
        
        # Computing metric
        if len(set(y[new_train_inds])) > 1:
            new_classifier = classifier(**alpha)
            new_classifier.fit(X[new_train_inds], y[new_train_inds])

            if (classifier) == type(GaussianNB()):
                new_probs = new_classifier.predict_proba(X_test.toarray())
            else:
                new_probs = new_classifier.predict_proba(X_test)

            if option == 'log':
                util = Strategy2.log_gain(new_probs, y_test)

            elif option == 'auc':
                auc = metrics.roc_auc_score(y_test, new_probs[:,1])
                util = auc
            elif option == 'accu':
                pred_y = model.classes_[np.argmax(new_probs, axis=1)]
                    
                accu = metrics.accuracy_score(y_test, pred_y)
                util = accu

        # If there was improvement, keep it; otherwise undo
        if util > previous_util:
            current_train_indices = new_train_inds
            pool = set(new_pool)
            previous_util = util

    return list(current_train_indices), set(pool)

"""
Mix the usage of strategy1 and strategy2, randomly, based on current_temperature.
On beginning, strategy1 tend to be more used.
temperature_step reduces current_temperature and it makes strategy2 to be more used than strategy1 later on.
"""
class SimulatedAnnealing(BaseStrategy):

    def __init__(self, strategy1=None, strategy2=None, inicial_temperature=.99, temperature_step=.01, seed=0):
        super(SimulatedAnnealing, self).__init__(seed=seed)
        self.strategy1 = strategy1
        self.strategy2 = strategy2
        self.current_temperature = inicial_temperature
        self.temperature_step = temperature_step

    def chooseNext(self, pool=None, X=None, model=None, k=1, current_train_indices = None, current_train_y = None):
        r = self.randgen.random()
        """
        Roll a dice, if true strategy1 is executed; otherwise strategy2
        """
        if r < self.current_temperature:
            pass
            out = self.strategy1.chooseNext(pool, X, model, k, current_train_indices, current_train_y)
        else:
            pass
            out = self.strategy2.chooseNext(pool, X, model, k, current_train_indices, current_train_y)

        self.current_temperature -= self.temperature_step
        return out





