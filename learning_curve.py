'''
Created on Jan 30, 2014

@author: mbilgic

For now, the program is handling just binary classification

'''

import argparse
import math
import sys
import numpy as np
import matplotlib.pyplot as plt

from collections import defaultdict
from time import time
from scipy import sparse

from sklearn import metrics

from sklearn.naive_bayes import MultinomialNB, GaussianNB, BernoulliNB
from sklearn.ensemble import RandomForestClassifier, AdaBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier


from sklearn.datasets import load_svmlight_file

from sklearn.cross_validation import train_test_split

from instance_strategies import LogGainStrategy, RandomStrategy, UncStrategy, RotateStrategy, BootstrapFromEach, QBCStrategy, ErrorReductionStrategy, Strategy1, Strategy2, makeItBetter, SimulatedAnnealing

def inVector(vector, value):

    try:
        a = vector.index(value)
        return True
    except:
        return False


def datasetReduction(X_train, y_train, m):
    choice = True
    count = 0

    aux_set = range(len(y_train))
    set_reduction = []
    while (count < m):
        pos = np.random.choice(aux_set)
        if y_train[pos] == int(choice) and not inVector(set_reduction, pos):
            set_reduction.append(pos)
            choice = not choice
            count += 1

    np.random.shuffle(set_reduction)
    return X_train[set_reduction], y_train[set_reduction]


def distribution(y):
    class_0 = 1
    class_1 = 0

    group = y[0]

    for i in y[1:]:
        if i == group:
            class_0 += 1
        else:
            class_1 += 1

    print 'Class 0:', class_0
    print 'Class 1:', class_1

def choosingStrategies(strategy, classifier, seed, sub_pool, alpha, X_test, y_test, y_pool, s_parameter = []):

    it = 0

    if strategy == 'erreduct':
        active_s = ErrorReductionStrategy(classifier=classifier, seed=seed, sub_pool=sub_pool, classifier_args=alpha)
    elif strategy == 'loggain':
        active_s = LogGainStrategy(classifier=classifier, seed=seed, sub_pool=sub_pool, classifier_args=alpha)
    elif strategy == 'qbc':
        active_s = QBCStrategy(classifier=classifier, classifier_args=alpha)
    elif strategy == 'rand':    
        active_s = RandomStrategy(seed=seed)
    elif strategy == 'unc':
        active_s = UncStrategy(seed=seed, sub_pool=sub_pool)
    elif strategy == 's1':
        active_s = Strategy1(classifier=classifier, seed=seed, sub_pool=sub_pool, classifier_args=alpha, X_test = X_test, y_test = y_test, y_pool = y_pool, option = s_parameter)
    elif strategy == 's2':
        active_s = Strategy2(classifier=classifier, seed=seed, sub_pool=sub_pool, classifier_args=alpha, X_test = X_test, y_test = y_test, y_pool = y_pool, option = s_parameter)
        it = -1
    elif strategy == 'sim':
        if len(s_parameter) < 4:
            print '2 strategies need to be chosen in order to use Simulated Annealing strategy.'
            sys.exit()
        active_learning_strategy1, it = choosingStrategies(s_parameter[0], classifier, seed, sub_pool, alpha, X_test, y_test, y_pool)
        active_learning_strategy2, it = choosingStrategies(s_parameter[1], classifier, seed, sub_pool, alpha, X_test, y_test, y_pool)
        active_s = SimulatedAnnealing(strategy1=active_learning_strategy1, strategy2=active_learning_strategy2, seed=seed, inicial_temperature=float(s_parameter[2]), temperature_step=float(s_parameter[3]))
        it = -1

    return active_s, it

'''
Main function. This function is responsible for training and testing.
'''
def learning(num_trials, X_train, y_train, X_test, strategy, budget, step_size, sub_pool, boot_strap_size, classifier, alpha, y_test, m, s_parameter, mb):
    accuracies = defaultdict(lambda: [])
    aucs = defaultdict(lambda: [])

    for t in range(num_trials):
        if m > 0 and len(y_train) > m:
            
            np.random.seed(t)

            rand_indices = np.random.permutation(X_train.shape[0])
            X_pool = X_train[rand_indices[:m]]
            y_pool = y_train[rand_indices[:m]]
            
        else:
            X_pool = X_train
            y_pool = y_train

        print "trial", t

        # Gaussian Naive Bayes requires denses matrizes
        if (classifier) == type(GaussianNB()):
            X_pool_csr = X_pool.toarray()
        else:
            X_pool_csr = X_pool.tocsr()
    
        pool = set(range(len(y_pool)))

        trainIndices = []
        
        bootsrapped = False

        # Choosing strategy
        # if strategy == 'erreduct':
        #     active_s = ErrorReductionStrategy(classifier=classifier, seed=t, sub_pool=sub_pool, classifier_args=alpha)
        # elif strategy == 'loggain':
        #     active_s = LogGainStrategy(classifier=classifier, seed=t, sub_pool=sub_pool, classifier_args=alpha)
        # elif strategy == 'qbc':
        #     active_s = QBCStrategy(classifier=classifier, classifier_args=alpha)
        # elif strategy == 'rand':    
        #     active_s = RandomStrategy(seed=t)
        # elif strategy == 'unc':
        #     active_s = UncStrategy(seed=t, sub_pool=sub_pool)
        # elif strategy == 's1':
        #     active_s = Strategy1(classifier=classifier, seed=t, sub_pool=sub_pool, classifier_args=alpha, X_test = X_test, y_test = y_test, y_pool = y_pool, option = s_parameter)
        # elif strategy == 's2':
        #     active_s = Strategy2(classifier=classifier, seed=t, sub_pool=sub_pool, classifier_args=alpha, X_test = X_test, y_test = y_test, y_pool = y_pool, option = s_parameter)
        #     it = -1
        # elif strategy == 'sim':
        #     active_s = SimulatedAnnealing(seed=t)
        active_s, it = choosingStrategies(strategy, classifier, t, sub_pool, alpha, X_test, y_test, y_pool, s_parameter)

        model = None

        condition = True
        # Loop for prediction
        while (condition):
            if strategy == 's2':
                it+=1
                condition = it < budget and len(pool) > step_size
            else:
              condition = len(trainIndices) < budget and len(pool) > step_size


            if condition:
                
                if not bootsrapped:
                    newIndices = []
                    bootsrapped = True
                    if not strategy == 's2':
                        boot_s = BootstrapFromEach(t)
                        newIndices = boot_s.bootstrap(pool, y=y_pool, k=boot_strap_size)
                else:
                    newIndices = active_s.chooseNext(pool, X_pool_csr, model, k = step_size, current_train_indices = trainIndices, current_train_y = y_pool[trainIndices])

                pool.difference_update(newIndices)

                if strategy == 's2':
                    trainIndices = list(pool)
                else:
                    trainIndices.extend(newIndices)
                
                model = classifier(**alpha)
                
                if mb:
                    trainIndices, pool = makeItBetter(X_pool_csr, y_pool, X_test, y_test, current_train_indices = trainIndices, pool = list(pool), number_trials = sub_pool, classifier=classifier, alpha=alpha, option='auc', seed=t)

                auc = -np.inf
                accu = -np.inf

                if len(set(y_pool[trainIndices])) > 1:
                    model.fit(X_pool_csr[trainIndices], y_pool[trainIndices])

                    

                    # Prediction
                    
                    # Gaussian Naive Bayes requires denses matrizes
                    if (classifier) == type(GaussianNB()):
                        y_probas = model.predict_proba(X_test.toarray())
                    else:
                        y_probas = model.predict_proba(X_test)

                    # Metrics
                    auc = metrics.roc_auc_score(y_test, y_probas[:,1])     
                    
                    pred_y = model.classes_[np.argmax(y_probas, axis=1)]
                    
                    accu = metrics.accuracy_score(y_test, pred_y)
                
                accuracies[len(trainIndices)].append(accu)
                aucs[len(trainIndices)].append(auc)

    return accuracies, aucs
    

if (__name__ == '__main__'):
    
    print "Loading the data"
    
    t0 = time()

    ### Arguments Treatment ###
    parser = argparse.ArgumentParser()

    # Classifier
    parser.add_argument("-c","--classifier", choices=['KNeighborsClassifier', 'LogisticRegression', 'SVC', 'BernoulliNB',
                        'DecisionTreeClassifier', 'RandomForestClassifier', 'AdaBoostClassifier', 'GaussianNB', 'MultinomialNB'],
                        default='MultinomialNB', help="Represents the classifier that will be used (default: MultinomialNB) .")

    # Classifier's arguments
    parser.add_argument("-a","--arguments", default='',
                        help="Represents the arguments that will be passed to the classifier (default: '').")    

    # Data: Testing and training already split
    parser.add_argument("-d", '--data', nargs=2, metavar=('pool', 'test'),
                        default=["data/imdb-binary-pool-mindf5-ng11", "data/imdb-binary-test-mindf5-ng11"],
                        help='Files that contain the data, pool and test, and number of \
                        features (default: data/imdb-binary-pool-mindf5-ng11 data/imdb-binary-test-mindf5-ng11 27272).')
    
    # Data: Single file
    parser.add_argument("-sd", '--sdata', type=str, default='',
                        help='Single file that contains the data, it will be splitted (default: None).')

    # File: Name of file that will be written the results
    parser.add_argument("-f", '--file', type=str, default='',
                        help='This feature represents the name that will be written with the result. \
                        If it is left blank, the file will not be written (default: '' ).')

    # Number of Trials
    parser.add_argument("-nt", "--num_trials", type=int, default=10, help="Number of trials (default: 10).")

    # Strategies
    parser.add_argument("-st", "--strategies", choices=['erreduct', 'loggain', 'qbc', 'rand', 's1', 's2', 'sim', 'unc'], nargs='*',default=['rand'],
                        help="Represent a list of strategies for choosing next samples (default: rand).")

    # Boot Strap
    parser.add_argument("-bs", '--bootstrap', default=10, type=int, 
                        help='Sets the Boot strap (default: 10).')
    
    # Budget
    parser.add_argument("-b", '--budget', default=500, type=int,
                        help='Sets the budget (default: 500).')

    # Step size
    parser.add_argument("-sz", '--stepsize', default=10, type=int,
                        help='Sets the step size (default: 10).')

    # Sub pool size
    parser.add_argument("-sp", '--subpool', default=250, type=int,
                        help='Sets the sub pool size (default: 250).')

    # Set reduction
    parser.add_argument("-m", default=0, type=int,
                        help='Sets size of the reduction to be done in the dataset, expects a integer positive value (default: No reduction).')

    parser.add_argument("-p", default=['log'], type=str, nargs='*')

    parser.add_argument("-mb", "--makeitbetter", action="store_true")    


    # Parsing args
    args = parser.parse_args()

    # args.classifier is a string, eval makes it a class
    classifier = eval((args.classifier))

    # Parsing classifier's arguments
    model_arguments = args.arguments.split(',')

    alpha = {}

    for argument in model_arguments:
        if argument.find('=') >= 0:
            index, value = argument.split('=')
            alpha[index] = eval(value)

    # Two formats of data are possible, split into training and testing or not split
    if args.sdata:
        # Not Split, single file
        data = args.sdata
        
        X, y = load_svmlight_file(data)

        # Splitting 2/3 of data as training data and 1/3 as testing
        # Data selected randomly
        X_pool, X_test, y_pool, y_test = train_test_split(X, y, test_size=(1./3.), random_state=42)

    else:
        # Split data
        data_pool = args.data[0]
        data_test = args.data[1]

        X_pool, y_pool = load_svmlight_file(data_pool)
        num_pool, num_feat = X_pool.shape

        X_test, y_test = load_svmlight_file(data_test, n_features=num_feat)

    duration = time() - t0

    print
    print "Loading took %0.2fs." % duration
    print

    num_trials = args.num_trials
    strategies = args.strategies

    boot_strap_size = args.bootstrap
    budget = args.budget
    step_size = args.stepsize
    sub_pool = args.subpool
    
    filename = args.file
    
    duration = defaultdict(lambda: 0.0)

    accuracies = defaultdict(lambda: [])
    
    aucs = defaultdict(lambda: [])    
    
    num_test = X_test.shape[0]

    m = args.m

    s_parameter = args.p
    # Argument p is used for strategies 1 and 2, and Simulated Annealing.
    # If there is only one argument, it is for strategies 1 and 2.
    # If there are 2 arguments or even, it is for Simulated Annealing. But, only the first two are going to be used.
    if len(s_parameter) == 1:
        print 'one argument'
        s_parameter = s_parameter[0]

    # Main Loop
    for strategy in strategies:
        t0 = time()

        accuracies[strategy], aucs[strategy] = learning(num_trials, X_pool, y_pool, X_test, strategy, budget, step_size, sub_pool, boot_strap_size, classifier, alpha, y_test, m, s_parameter, args.makeitbetter)

        duration[strategy] = time() - t0

        print
        print "%s Learning curve took %0.2fs." % (strategy, duration[strategy])
        print
    
    
    values = sorted(accuracies[strategies[0]].keys())

    # print the accuracies
    print
    print "\t\tAccuracy mean"
    print "Train Size\t",
    for strategy in strategies:
        print "%s\t\t" % strategy,
    print

    for value in values:
        print "%d\t\t" % value,
        for strategy in strategies:
            print "%0.3f\t\t" % np.mean(accuracies[strategy][value]),
        print
        
    # print the aucs
    print
    print "\t\tAUC mean"
    print "Train Size\t",
    for strategy in strategies:
        print "%s\t\t" % strategy,
    print

    for value in values:
        print "%d\t\t" % value,
        for strategy in strategies:
            print "%0.3f\t\t" % np.mean(aucs[strategy][value]),
        print

    # print the times
    print
    print "\tTime"
    print "Strategy\tTime"

    for strategy in strategies:
        print "%s\t%0.2f" % (strategy, duration[strategy])

    # Creates file, if asked
    if filename:
        doc = open(filename, 'w')

    # plotting
    for strategy in strategies:
        accuracy = accuracies[strategy]
        auc = aucs[strategy]

        # Plotting Accuracy
        x = sorted(accuracy.keys())
        y = [np.mean(accuracy[xi]) for xi in x]
        # z = [np.std(accuracy[xi]) for xi in x]
        z = []
        for xi in x:
            std = []
            for elem in accuracy[xi]:
                aux = elem
                if np.isinf(elem):
                    aux = 0
                std.append(aux)
            z.append(np.std(std))
        e = np.array(z) / math.sqrt(num_trials)

        # plt.figure(1)
        # plt.subplot(211)
        # plt.plot(x, y, '-', label=strategy)
        # plt.legend(loc='best')
        # plt.title('Accuracy')

        # Saves all accuracies into a file
        if filename:
            doc.write(strategy+'\n'+'accuracy'+'\n')
            doc.write('train size,mean,standard deviation,standard error'+'\n')
            # print len(values),len(y), len(z), len(e)
            # print
            for i in range(len(y)):
                doc.write("%d,%f,%f,%f\n" % (values[i], y[i], z[i], e[i]))
            doc.write('\n')

        # Plotting AUC
        x = sorted(auc.keys())
        y = [np.mean(auc[xi]) for xi in x]
        # z = [np.std(auc[xi]) for xi in x]
        z = []
        for xi in x:
            std = []
            for elem in auc[xi]:
                aux = elem
                if np.isinf(elem):
                    aux = 0
                std.append(aux)
            z.append(np.std(std))
        e = np.array(z) / math.sqrt(num_trials)
          

        # plt.subplot(212)
        # plt.plot(x, y, '-', label=strategy)
        # plt.legend(loc='best')
        # plt.title('AUC')

        # Saves all acus into a file
        if filename:
            doc.write('AUC'+'\n')
            doc.write('train size,mean,standard deviation,standard error'+'\n')
            for i in range(len(y)):
                doc.write("%d,%f,%f,%f\n" % (values[i], y[i], z[i], e[i]))
            doc.write('\n\n\n')

    if filename:
        doc.close()
        # fig_name = filename.split('.')[0] + '.png'
        # plt.savefig(fig_name)
    # else:
        # plt.show()
