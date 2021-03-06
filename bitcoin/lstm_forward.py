#!/opt/sharcnet/python/2.7.5/gcc/bin/python
from __future__ import print_function
import numpy as np
import time
import theano
import theano.tensor as T
import lasagne
from label_data import label_data
from iterate_minibatch import iterate_minibatches
from lasagne.regularization import regularize_layer_params, l2, l1

lamda = 0.5

WINDOW = 50

N_HIDDEN = 128
# Number of training sequences in each batch
N_BATCH = 2000
# Optimization learning rate
LEARNING_RATE = .01
# All gradients above this will be clipped
GRAD_CLIP = 200
# How often should we check the output?

NUM_EPOCHS = 300


a = np.load("/scratch/rqiao/okcoin/labeled-02-12:18.npz")
data = a['arr_0']
timestamp = a['arr_1']
label = a['arr_2']
#scale price:
priceIndex = np.linspace(0,18,10,dtype=np.int8)
price = data[:,priceIndex]
meanPrice = price.mean()
stdPrice = price.std()
price = (price-meanPrice)/stdPrice
data[:,priceIndex] = price
volumeIndex = np.linspace(1,19,10,dtype=np.int8)
for index in volumeIndex:
    volume = data[:,index]
    meanVolume = volume.mean()
    stdVolume = volume.std()
    volume = (volume-meanVolume)/stdVolume
    data[:,index] = volume
#data split
train_data, train_label = data[:-20200,:20], label[:-20200]
valid_data, valid_label = data[-20200:-10100,:20], label[-20200:-10100]
test_data, test_label = data[-10100:,:20], label[-10100:]

def main(num_epochs=NUM_EPOCHS):
    print("Building network ...")
    # First, we build the network, starting with an input layer
    # Recurrent layers expect input of shape
    # (batch size, max sequence length, number of features)
    l_in = lasagne.layers.InputLayer(shape=(N_BATCH, WINDOW, 20))

    l_forward = lasagne.layers.LSTMLayer(
        l_in, N_HIDDEN, grad_clipping=GRAD_CLIP, only_return_final=True)
    # Our output layer is a simple dense connection, with 1 output unit
    l_out = lasagne.layers.DenseLayer(
        lasagne.layers.DropoutLayer(l_forward), num_units=3, nonlinearity=lasagne.nonlinearities.softmax)

    target_values = T.ivector('target_output')

    prediction = lasagne.layers.get_output(l_out)
    test_prediction = lasagne.layers.get_output(l_out,deterministic=True)
    loss = lasagne.objectives.categorical_crossentropy(prediction, target_values)
    l1_penalty = regularize_layer_params(l_out, l1)
    test_loss = loss.mean()
    loss = test_loss + lamda *  l1_penalty
    acc = T.mean(T.eq(T.argmax(test_prediction, axis=1), target_values),dtype=theano.config.floatX)

    all_params = lasagne.layers.get_all_params(l_out)
    LEARNING_RATE = .01
    print("Computing updates ...")
    updates = lasagne.updates.nesterov_momentum(loss, all_params,LEARNING_RATE,0.95)
    # Theano functions for training and computing cost
    print("Compiling functions ...")
    train = theano.function([l_in.input_var, target_values],
                            loss, updates=updates)
    valid = theano.function([l_in.input_var, target_values],
                            [test_loss, acc])
    accuracy = theano.function(
        [l_in.input_var, target_values],acc )

    result = theano.function([l_in.input_var],prediction)

    best_acc=0
    best_val_err = 10000
    flag = 0
    print("Training ...")
    try:
        for epoch in range(NUM_EPOCHS):
            if epoch - flag > 10:
                LEARNING_RATE *= 0.2
                updates = lasagne.updates.nesterov_momentum(loss, all_params,LEARNING_RATE,0.95)
                train = theano.function([l_in.input_var, target_values],
                                        loss, updates=updates)
            train_err = 0
            train_batches = 0
            start_time = time.time()
            for batch in iterate_minibatches(train_data, train_label, N_BATCH, WINDOW):
                inputs, targets = batch
                train_err += train(inputs, targets)
                train_batches += 1

            val_err = 0
            val_acc = 0
            val_batches = 0
            for batch in iterate_minibatches(valid_data, valid_label, N_BATCH, WINDOW):
                inputs, targets = batch
                err, acc = valid(inputs, targets)
                val_err += err
                val_acc += acc
                val_batches += 1

            val_acc = val_acc / val_batches
            val_err = val_err / val_batches)
            if val_acc > best_acc:
                best_acc = val_acc
            if val_err < best_val_err:
                best_val_err = val_err
                flag = epoch
            # Then we print the results for this epoch:
            print("Epoch {} of {} took {:.3f}s".format(
                epoch + 1, NUM_EPOCHS, time.time() - start_time))
            print("  training loss:\t\t{:.6f}".format(train_err / train_batches))
            print("  validation loss:\t\t{:.6f}".format(val_err))
            print("  validation accuracy:\t\t{:.2f} %".format(
                    val_acc * 100))
    except KeyboardInterrupt:
        pass
if __name__ == '__main__':
    main()
