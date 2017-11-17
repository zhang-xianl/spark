# -*- coding: utf-8 -*-
import sys
import argparse
import numpy as np
from operator import add
import time
from pyspark import SparkContext


def readData(input_file,spark_context):
    """  Read data from an input file and return rdd containing pairs of the form:
	                 (x,y)
	 where x is a numpy array and y is a real value. The input file should be a 
	 'comma separated values' (csv) file: each line of the file should contain x
         followed by y. For example, line:

         1.0,2.1,3.1,4.5

         should be converted to tuple:
	
         (array(1.0,2.1,3.1),4.5)
	 

    """ 
    return spark_context.textFile(input_file)\
		.map(lambda line:line.split(','))\
		.map(lambda words:(words[:-1],words[-1]))\
		.map(lambda (features,target): (np.array([ float(x) for x in features]),float(target)))



def readBeta(input):
    """ Read a vector β from CSV file input
    """
    with open(input,'r') as fh:
        str_list = fh.read()\
                   .strip()\
		   .split(',')
        return np.array( [float(val) for val in str_list] )           

def writeBeta(output,beta):
    """ Write a vector β to a CSV file ouptut
    """
    with open(output,'w') as fh:
	fh.write(','.join(map(str, beta.tolist()))+'\n')
    



def estimateGrad(fun,x,delta):
     """ Given a real-valued function fun, estimate its gradient numerically.
     """
     d = len(x)
     grad = np.zeros(d)
     for i in range(d):
         e = np.zeros(d)
         e[i] = 1.0
         grad[i] = (fun(x+delta*e) - fun(x))/delta
     return grad

 
def lineSearch(fun,x,grad,a=0.2,b=0.6):
    """ Given function fun, a current argument x, and gradient grad, 
	perform backtracking line search to find the next point to move to.
	(see Boyd and Vandenberghe, page 464).

	Parameters a,b  are the parameters of the line search.

        Given function fun, and current argument x, and gradient  ∇fun(x), the function finds a t such that
	fun(x - t * grad) <= fun(x) - a t <∇fun(x),∇fun(x)>

	The return value is the resulting value of t.
    """
    t = 1.0
    while fun(x-t*grad) > fun(x)- a * t *np.dot(grad,grad):
	t = b * t
    return t 
    


def predict(x,beta):
    """ Given vector x containing features and parameter vector β, 
	return the predicted value: 

	                y = <x,β>   

    """
    return np.dot(x,beta)




def f(x,y,beta):
    """ Given vector x containing features, true label y, 
	and parameter vector β, return the square error:

	         f(β;x,y) =  (y - <x,β>)^2	

    """
    return np.square(y - np.dot(x, beta))






def localGradient(x,y,beta):
    """ Given vector x containing features, true label y, 
	and parameter vector β, return the gradient ∇f of f:

	        ∇f(β;x,y) =  -2 * (y - <x,β>) * x	

        with respect to parameter vector β.

        The return value is  ∇f.
    """
    inside = y - np.dot(x, beta) 
    return -2.0 * inside *x

 

def F(data,beta,lam = 0):
    """  Compute the regularized mean square error:

             F(β) = 1/n Σ_{(x,y) in data}    f(β;x,y)  + λ ||β ||_2^2   
                  = 1/n Σ_{(x,y) in data} (y- <x,β>)^2 + λ ||β ||_2^2 

         where n is the number of (x,y) pairs in RDD data. 

	 Inputs are:
            - data: an RDD containing pairs of the form (x,y)
            - beta: vector β
	    - lam:  the regularization parameter λ
           

	 The return value is F(β).

    """
    beta2 = np.sum(np.square(beta))
    sum, n = data.map(lambda (x,y): (f(x, y ,beta),1))\
                 .reduce(lambda x, y: (x[0] + y[0], x[1] + y[1]))
    return (1.0 / n) * sum + lam * beta2


def gradient(data,beta,lam = 0):
    """ Compute the gradient  ∇F of the regularized mean square error 
                F(β) = 1/n Σ_{(x,y) in data} f(β;x,y) + λ ||β ||_2^2   
                     = 1/n Σ_{(x,y) in data} (y- <x,β>)^2 + λ ||β ||_2^2   
 
	where n is the number of (x,y) pairs in data. 

	Inputs are:
             - data: an RDD containing pairs of the form (x,y)
             - beta: vector β
	     - lam:  the regularization parameter λ
             

        The return value is an array containing ∇F.

    """
    gradSum,n = data.map(lambda(x,y): (localGradient(x,y,beta),1))\
                    .reduce(lambda x, y: (x[0] + y[0], x[1] + y[1]))
    return (1.0 / n) * gradSum + lam * 2 * beta 

def test(data,beta):
    """ Compute the mean square error  

		 MSE(β) =  1/n Σ_{(x,y) in data} (y- <x,β>)^2

        of parameter vector β over the dataset contained in RDD data, where n is the size of RDD data.
        
	Inputs are:
             - data: an RDD containing pairs of the form (x,y)
             - beta: vector β

	The return value is MSE(β).  
       
    """
    return F(data,beta,0)




def train(data,beta_0, lam,max_iter,eps):
    """ Perform gradient descent:


        to  minimize F given by
  
             F(β) = 1/n Σ_{(x,y) in data} f(β;x,y) + λ ||β ||_2^2   

	where
             - data: an rdd containing pairs of the form (x,y)
             - beta_0: the starting vector β
	     - lam:  is the regularization parameter λ
             - max_iter: maximum number of iterations of gradient descent
             - eps: upper bound on the l2 norm of the gradient
             - a,b: parameters used in backtracking line search


	The function performs gradient descent with a gain found through backtracking
        line search. That is it computes

                   
	           β_k+1 = β_k - γ_k ∇F(β_k) 
		
	where the gain γ_k is given by
	
		  γ_k = lineSearch(F,β_κ,∇F(β_k))

	and terminates after max_iter iterations or when ||∇F(β_k)||_2<ε.   

	The function returns:
	     -beta: the trained β, 
	     -gradNorm: the norm of the gradient at the trained β, and
             -k: the number of iterations performed
    """ 
    tIni = time.time()	
    beta = 1.0 *beta_0
    for k in range(max_iter):
        PresentFValue = F (data, beta, lam)
        GradF = gradient(data, beta, lam)
        normGradF = np.sqrt(np.sum(np.square(GradF)))
        if normGradF < eps:
            return beta,normGradF,k
        tFinal = time.time()
        print'Iteration Time', k+1, 'time',tFinal - tIni,'Function Value', PresentFValue, 'Norm', normGradF
        gamma = lineSearch(lambda x: F(data,x,lam), beta, GradF)
        beta = beta - gamma * GradF * 1.0
    return beta, normGradF,k
     

   
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = 'Parallel Ridge Regression.',formatter_class=argparse.ArgumentDefaultsHelpFormatter)    
    parser.add_argument('--traindata',default=None, help='Input file containing (x,y) pairs, used to train a linear model')
    parser.add_argument('--testdata',default=None, help='Input file containing (x,y) pairs, used to test a linear model')
    parser.add_argument('--beta', default='beta', help='File where beta is stored (when training) and read from (when testing)')
    parser.add_argument('--lam', type=float,default=0.0, help='Regularization parameter λ')
    parser.add_argument('--max_iter', type=int,default=100, help='Maximum number of iterations')
    parser.add_argument('--eps', type=float, default=0.01, help='ε-tolerance. If the l2_norm gradient is smaller than ε, gradient descent terminates.') 
    parser.add_argument('--N',type=int,default=2,help='Level of parallelism')


    verbosity_group = parser.add_mutually_exclusive_group(required=False)
    verbosity_group.add_argument('--verbose', dest='verbose', action='store_true')
    verbosity_group.add_argument('--silent', dest='verbose', action='store_false')
    parser.set_defaults(verbose=True)

    args = parser.parse_args()
  
    sc = SparkContext(appName='Parallel Ridge Regression')
    
    if not args.verbose :
        sc.setLogLevel("ERROR")	
  
    beta = None

    if args.traindata is not None:
        # Train a linear model β from data with regularization parameter λ, and store it in beta
        print 'Reading training data from',args.traindata
        data = readData(args.traindata,sc)
        data = data.repartition(args.N).cache()
      
        x,y = data.take(1)[0]
        beta0 = np.zeros(len(x))

	print 'Training on data from',args.traindata,'with λ =',args.lam,', ε =',args.eps,', max iter = ',args.max_iter
        beta, gradNorm, k = train(data,beta_0=beta0,lam=args.lam,max_iter=args.max_iter,eps=args.eps) 
	print 'Algorithm ran for',k,'iterations. Converged:',gradNorm<args.eps
	print 'Saving trained β in',args.beta
        writeBeta(args.beta,beta)
        
     
    if args.testdata is not None:
        # Read beta from args.beta, and evaluate its MSE over data
        print 'Reading test data from',args.testdata
        data = readData(args.testdata,sc)
        data = data.repartition(args.N).cache()
      
        print 'Reading beta from',args.beta
	beta = readBeta(args.beta)

	print 'Computing MSE on data',args.testdata
        MSE = test(data,beta)
	print 'MSE is:', MSE 
	
