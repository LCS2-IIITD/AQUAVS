# -*- coding: utf-8 -*-
"""FashionMNIST_SVAE.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1RGZCc5UM4co2XBKW3wA-TuTo6KFIxZh_
"""

datasetName = "FashionMNIST"

import numpy as np
import tensorflow as tf
from tensorflow.keras import backend as K

from tensorflow.keras.models import Model
from tensorflow.keras.layers import Conv2D, Conv2DTranspose, Input, Flatten, Dense, Lambda, Reshape, BatchNormalization, MaxPooling2D, Dropout
from tensorflow.keras import backend as K
import tensorflow.keras as keras
import matplotlib.pyplot as plt
from scipy.stats import norm

def vae_loss(data, reconstruction):
    z_mean, z_log_var, z = encoder(data)
    reconstruction_loss = keras.losses.binary_crossentropy(data, reconstruction)
    reconstruction_loss = tf.reduce_mean(reconstruction_loss, axis=[1,2])
    kl_loss = 1 + z_log_var - tf.square(z_mean) - tf.exp(z_log_var)
    kl_loss = tf.reduce_mean(kl_loss, axis=1)
    kl_loss *= -0.5
    total_loss = tf.reduce_mean(reconstruction_loss + kl_loss)/100
    return total_loss

def sampling(args):
    z_mean, z_var = args
    epsilon = K.random_normal(shape=(K.shape(z_mean)[0], latent_dim), mean=0,)  ## latent_dim = K.shape(z_mean)[1] 
    return z_mean + K.exp(z_var / 2) * epsilon


img_dimensions = (28, 28, 1)

latent_dim = 100
batch_size = 32
num_channels = 1

## ENCODER
inputNode = Input(shape=img_dimensions, name="EncoderInput")
enc_inter = Conv2D(filters=32, kernel_size=4, strides=2, padding='same', kernel_initializer='he_uniform')(inputNode)
enc_inter = Conv2D(filters=64, kernel_size=4, strides=2, padding='same', kernel_initializer='he_uniform', activation='relu')(enc_inter)
enc_inter = Conv2D(filters=128, kernel_size=4, strides=1, padding='same', kernel_initializer='he_uniform', activation=tf.nn.relu)(enc_inter)

conv_shape = K.int_shape(enc_inter) 

enc_inter = Flatten()(enc_inter)
z_mean = Dense(latent_dim, name="Mean")(enc_inter)
z_var = Dense(latent_dim, name="Variance")(enc_inter)
z = Lambda(sampling, output_shape=(latent_dim,))([z_mean, z_var])
encoder = Model(inputNode, [z_mean, z_var, z], name="Encoder")


## CLASSIFIER
clf_latent_inputs = Input(shape=(latent_dim,), name='ClassifierInput')
clf_outputs = Dense(10, activation='softmax', name='ClassifierOutput')(clf_latent_inputs)
clf_supervised = Model(clf_latent_inputs, clf_outputs, name='Classifier')


## DECODER
inputNode2 = Input(shape=(latent_dim,), name="DecoderInput")
dec_inter = Dense(conv_shape[1]*conv_shape[2]*conv_shape[3])(inputNode2)
dec_inter = Reshape((conv_shape[1], conv_shape[2], conv_shape[3]))(dec_inter)
dec_inter = Conv2DTranspose(filters=128, kernel_size=4, strides=1, padding='same', kernel_initializer='he_uniform', activation='relu')(dec_inter)
dec_inter = Conv2DTranspose(filters=64, kernel_size=4, strides=2, padding='same', kernel_initializer='he_uniform', activation='relu')(dec_inter)
dec_inter = Conv2DTranspose(filters=32, kernel_size=4, strides=2, padding='same', kernel_initializer='he_uniform', activation='relu')(dec_inter)
decoder_node = Conv2DTranspose(num_channels, kernel_size=4, strides=1, padding='same')(dec_inter)
decoder = Model(inputNode2, decoder_node, name='Decoder')

output_combined = [decoder(encoder(inputNode)[2]), clf_supervised(encoder(inputNode)[2])]
vae = Model(inputNode, output_combined, name='S-VAE')

encoder.summary()
decoder.summary()
clf_supervised.summary()
vae.summary()

vae.compile(optimizer='adam', loss=[vae_loss, 'categorical_crossentropy'])

from collections import defaultdict 
import random
import numpy as np
from sklearn.utils import shuffle
from scipy import stats
from sklearn.metrics import precision_score, recall_score, accuracy_score 
from collections import Counter


#grouping datapoints by respective classes
def group_data_by_class(input_x, input_y):
    final_out = defaultdict(list) 
    final_idx = defaultdict(list)
    for i in range(input_x.shape[0]): 
        final_out[input_y[i]].append(input_x[i])
        final_idx[input_y[i]].append(i)
    return final_out, final_idx


#Ref - https://core.ac.uk/download/pdf/206095228.pdf
def outlier_detection_med_mad(input_data, k1):
    column_med = np.median(input_data, axis = 0)
    column_mad = stats.median_absolute_deviation(input_data,axis = 0)

    #computing threshold for each feature
    threshold_lower = column_med - (k1*column_mad)
    threshold_upper = column_med + (k1*column_mad)
    outliers = []
    num_outlier_feature_list = []
    outlier_level = defaultdict(list)
    for i in range(input_data.shape[0]):
        num_outlier_feature = 0
        x = input_data[i]
        for id in range(x.shape[0]):
            if not (threshold_lower[id] <= x[id] and x[id] <= threshold_upper[id]):
                num_outlier_feature += 1
        outlier_level[num_outlier_feature].append(i)
    return outlier_level


# computes noise level of each datapoint 
def get_train_lvl(input_x, input_y, MAD_Outlier_constant):
    grouped_train, grouped_idx = group_data_by_class(input_x, input_y.reshape(input_y.shape[0]))
    cntr = 0
    train_lvl = [-1 for i in range(input_x.shape[0])]
    for digit in range(0,10):
        z_values = encoder.predict(np.array(grouped_train[digit]))[2]
        class_outliers = outlier_detection_med_mad(z_values, MAD_Outlier_constant)
        for i in class_outliers.keys():
            for j in class_outliers[i]:
                # i is the outlier level
                # grouped_idx[digit][j] is the index
                train_lvl[grouped_idx[digit][j]] = i
    return np.array(train_lvl)


#adds noise to y-labels using uniform noise model - i.e. mislabeled samples are given labels uniformly at random.
def add_noise_UniformNoiseModel(input_y, perc, allClasses):
    final_idx = defaultdict(list)
    noisy_y = [-1 for i in range(input_y.shape[0])]
    
    for i in range(input_y.shape[0]): 
        final_idx[input_y[i]].append(i)
        
    for lbl in final_idx.keys():
        remC = (perc/100.0)*len(final_idx[lbl])
        #print("Label: ", lbl, "; # of datapoints flipped: ", int(remC))
        for i in range(int(remC)):
            idx = random.randint(0, len(final_idx[lbl]) - 1)
            newLabel = random.choice(allClasses)
            while (newLabel == lbl):
                newLabel = random.choice(allClasses)
            noisy_y[final_idx[lbl][idx]] = newLabel  # update the label for datapoint from `label` to `newLabel` 
            del final_idx[lbl][idx]
    
    for lbl in final_idx.keys():
        for i in final_idx[lbl]:
            noisy_y[i] = lbl
    
    return np.array(noisy_y)

#adds noise to y-labels using systematic noise model - i.e. mislabeled samples are given labels systematic at random.
def add_noise_SystematicNoiseModel(input_y, perc, allClasses):
    final_idx = defaultdict(list)
    noisy_y = [-1 for i in range(input_y.shape[0])]
    
    for i in range(input_y.shape[0]): 
        final_idx[input_y[i]].append(i)
        
    for lbl in final_idx.keys():
        remC = (perc/100.0)*len(final_idx[lbl])
        #print("Label: ", lbl, "; # of datapoints flipped: ", int(remC))
        for i in range(int(remC)):
            idx = random.randint(0, len(final_idx[lbl]) - 1)
            newLabel = (lbl + 1)%(len(allClasses))
            noisy_y[final_idx[lbl][idx]] = newLabel  # update the label for datapoint from `label` to `newLabel` 
            del final_idx[lbl][idx]
    
    for lbl in final_idx.keys():
        for i in final_idx[lbl]:
            noisy_y[i] = lbl
    
    return np.array(noisy_y)


# min-max normalization
def min_max_normalize(lis):
    minL = float(min(lis))
    maxL = float(max(lis))
    minMaxLis = [float((float(x) - minL)/ (maxL - minL)) for x in lis]
    return minMaxLis

(train_data, train_labels), (test_data, test_labels) = tf.keras.datasets.fashion_mnist.load_data()

#reshaping
test_data = test_data.reshape((test_data.shape[0], 28, 28, 1))
train_data = train_data.reshape((train_data.shape[0], 28, 28, 1))
test_labels = test_labels.reshape(test_labels.shape[0])
train_labels = train_labels.reshape(train_labels.shape[0])

# convert from integers to floats
train_data = train_data.astype('float32')
test_data = test_data.astype('float32')

# normalize to range 0-1
train_data = train_data / 255.0
test_data = test_data / 255.0

noisePerc = 20 # percentage noise
noiseType = "Sys"
if(noiseType == "Sys"):
    noisy_labels = add_noise_SystematicNoiseModel(train_labels, noisePerc, [cl for cl in range(10)])
elif(noiseType == "Uni"):
    noisy_labels = add_noise_UniformNoiseModel(train_labels, noisePerc, [cl for cl in range(10)])

grn_truth = np.array(noisy_labels == train_labels, dtype=int)

print("Number of mislabelled: ", len(grn_truth) - sum(grn_truth), "out of", len(grn_truth))

y_enc_noisy_labels = tf.keras.utils.to_categorical(noisy_labels) #encode noisy labels

# callback definitions

def scheduler(epoch):
    return 0.001/(epoch+1)

earlyStopCallback = tf.keras.callbacks.EarlyStopping(
    monitor="val_loss",
    min_delta=0,
    patience=0,
    verbose=0,
    mode="auto",
    baseline=None,
    restore_best_weights=True,
)

lrScheduler = tf.keras.callbacks.LearningRateScheduler(scheduler)

splitID = int(0.8*len(train_data))

#Note - VAE trains on noisy data

vae.fit(train_data[:splitID], [train_data[:splitID], y_enc_noisy_labels[:splitID]], 
        shuffle=True, epochs=15, batch_size=32, 
        validation_data=(train_data[splitID:], [train_data[splitID:], y_enc_noisy_labels[splitID:]]), 
        callbacks=[lrScheduler, earlyStopCallback],
        verbose=1)

noisy_lvl = get_train_lvl(train_data, noisy_labels, 1.5)

np.save(str(noisePerc) + "_NoisyLabels_" + datasetName + ".npy", noisy_labels)   #save noisy labels
np.save(str(noisePerc) + "_NoiseLevels_" + datasetName +".npy", noisy_lvl)  # save noise scores