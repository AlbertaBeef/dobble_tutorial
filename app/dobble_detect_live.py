#
# Dobble Buddy - Detection/Classification (live with USB camera)
#
# References:
#   https://www.kaggle.com/grouby/dobble-card-images
#
# Dependencies:
#


import numpy as np
import cv2
import os
from datetime import datetime
import itertools

#import keras
#from keras.models import load_model
#from keras.utils import to_categorical

#from imutils.video import FPS

from ctypes import *
from typing import List
import xir
import pathlib
import vart
#import threading
import time
import sys
import argparse
import glob
import subprocess
import re
import dobble_utils as db

def get_media_dev_by_name(src):
    devices = glob.glob("/dev/media*")
    for dev in sorted(devices):
        proc = subprocess.run(['media-ctl','-d',dev,'-p'], capture_output=True, encoding='utf8')
        for line in proc.stdout.splitlines():
            if src in line:
                return dev

def get_video_dev_by_name(src):
    devices = glob.glob("/dev/video*")
    for dev in sorted(devices):
        proc = subprocess.run(['v4l2-ctl','-d',dev,'-D'], capture_output=True, encoding='utf8')
        for line in proc.stdout.splitlines():
            if src in line:
                return dev

# ...work in progress ...
#def detect_dpu_architecture():
#    proc = subprocess.run(['xdputil','query'], capture_output=True, encoding='utf8')
#    for line in proc.stdout.splitlines():
#        if 'DPU Arch' in line:
#            #                 "DPU Arch":"DPUCZDX8G_ISA0_B128_01000020E2012208",
#            #dpu_arch = re.search('DPUCZDX8G_ISA0_(.+?)_', line).group(1)  
#            #                 "DPU Arch":"DPUCZDX8G_ISA1_B2304",
#            #dpu_arch = re.search('DPUCZDX8G_ISA1_(.+?)', line).group(1)
#            return dpu_arch

# Parameters (tweaked for video)
dir = './dobble-dataset'

scale = 1.0

global circle_minRadius
global circle_maxRadius

circle_minRadius = int(100*scale)
circle_maxRadius = int(200*scale)
circle_xxxRadius = int(250*scale)

b = int(4*scale) # border around circle for bounding box

text_fontType = cv2.FONT_HERSHEY_SIMPLEX
text_fontSize = 0.75*scale
text_color    = (0,0,255)
text_lineSize = max( 1, int(2*scale) )
text_lineType = cv2.LINE_AA

matching_x = int(10*scale)
matching_y = int(20*scale)


print("[INFO] Searching for USB camera ...")
dev_video = get_video_dev_by_name("uvcvideo")
dev_media = get_media_dev_by_name("uvcvideo")
print(dev_video)
print(dev_media)

#input_video = 0 
input_video = dev_video  
print("[INFO] Input Video : ",input_video)

displayReference = True

captureAll = False
output_dir = './captured-images'

if not os.path.exists(output_dir):      
    os.mkdir(output_dir)            # Create the output directory if it doesn't already exist

def set_minRadius(*arg):
    global circle_minRadius
    circle_minRadius = int(arg[0])
    print("[minRadius] ",circle_minRadius)
    #pass
    
def set_maxRadius(*arg):
    global circle_maxRadius
    circle_maxRadius = int(arg[0])
    print("[maxRadius] ",circle_maxRadius)
    #pass
    
    
cv2.namedWindow('Dobble Classification')
cv2.createTrackbar('minRadius', 'Dobble Classification', circle_minRadius, circle_xxxRadius, set_minRadius)
cv2.createTrackbar('maxRadius', 'Dobble Classification', circle_maxRadius, circle_xxxRadius, set_maxRadius)


# Open video
cap = cv2.VideoCapture(input_video)
frame_width = 640
frame_height = 480
cap.set(cv2.CAP_PROP_FRAME_WIDTH,frame_width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT,frame_height)
#frame_width = int(round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
#frame_height = int(round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
print("camera",input_video," (",frame_width,",",frame_height,")")

# Open dobble model
#model = load_model('dobble_model.h5')

# Vitis-AI implemenation of dobble model

def get_subgraph (g):
    sub = []
    root = g.get_root_subgraph()
    sub = [ s for s in root.toposort_child_subgraph()
            if s.has_attr("device") and s.get_attr("device").upper() == "DPU"]
    return sub

def get_child_subgraph_dpu(graph: "Graph") -> List["Subgraph"]:
    assert graph is not None, "'graph' should not be None."
    root_subgraph = graph.get_root_subgraph()
    assert (root_subgraph is not None), "Failed to get root subgraph of input Graph object."
    if root_subgraph.is_leaf:
        return []
    child_subgraphs = root_subgraph.toposort_child_subgraph()
    assert child_subgraphs is not None and len(child_subgraphs) > 0
    return [
        cs
        for cs in child_subgraphs
        if cs.has_attr("device") and cs.get_attr("device").upper() == "DPU"
    ]



"""
Calculate softmax
data: data to be calculated
size: data size
return: softamx result
"""
import math
def CPUCalcSoftmax(data, size):
    sum = 0.0
    result = [0 for i in range(size)]
    for i in range(size):
        result[i] = math.exp(data[i])
        sum += result[i]
    for i in range(size):
        result[i] /= sum
    return result

"""
Get topk results according to its probability
datain: data result of softmax
filePath: filePath in witch that records the infotmation of kinds
"""

def TopK(datain, size, filePath):

    cnt = [i for i in range(size)]
    pair = zip(datain, cnt)
    pair = sorted(pair, reverse=True)
    softmax_new, cnt_new = zip(*pair)
    fp = open(filePath, "r")
    data1 = fp.readlines()
    fp.close()
    for i in range(5):
        idx = 0
        for line in data1:
            if idx == cnt_new[i]:
                print("Top[%d] %d %s" % (i, idx, (line.strip)("\n")))
            idx = idx + 1

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()  
ap.add_argument('-m', '--model',     type=str, default='asl_classifier.xmodel', help='Path of xmodel. Default is asl_classifier.xmodel')

args = ap.parse_args()  
  
print ('Command line options:')
print (' --model     : ', args.model)

#dpu_arch = detect_dpu_architecture()
#print('[INFO] Detected DPU architecture : ',dpu_arch)
#
#model_path = './model/'+dpu_arch+'/dobble_classifier.xmodel'
#print('[INFO] Dobble model : ',model_path)
model_path = args.model

# Create DPU runner
g = xir.Graph.deserialize(model_path)
subgraphs = get_child_subgraph_dpu(g)
assert len(subgraphs) == 1 # only one DPU kernel
dpu = vart.Runner.create_runner(subgraphs[0], "run")
# input scaling
input_fixpos = dpu.get_input_tensors()[0].get_attr("fix_point")
input_scale = 2**input_fixpos
print('[INFO] input_fixpos=',input_fixpos,' input_scale=',input_scale)

# Get input/output tensors
inputTensors = dpu.get_input_tensors()
outputTensors = dpu.get_output_tensors()
inputShape = inputTensors[0].dims
outputShape = outputTensors[0].dims

# Load reference images
train1_dir = dir+'/dobble_deck01_cards_57'
train1_cards = db.capture_card_filenames(train1_dir)
train1_X,train1_y = db.read_and_process_image(train1_cards,72,72)

# Load mapping/symbol databases
symbols = db.load_symbol_labels(dir+'/dobble_symbols.txt')
mapping = db.load_card_symbol_mapping(dir+'/dobble_card_symbol_mapping.txt')

print("================================")
print("Dobble Classification Demo:")
print("\tPress ESC to quit ...")
print("\tPress 'p' to pause video ...")
print("\tPress 'c' to continue ...")
print("\tPress 's' to step one frame at a time ...")
print("\tPress 'w' to take a photo ...")
print("================================")

step = False
pause = False

image = []
output = []
circle_list = []
bbox_list = []
card_list = []

frame_count = 0

# start the FPS counter
#fps = FPS().start()

# init the real-time FPS counter
rt_fps_count = 0
rt_fps_time = cv2.getTickCount()
rt_fps_valid = False
rt_fps = 0.0
rt_fps_message = "FPS: {0:.2f}".format(rt_fps)
rt_fps_x = int(10*scale)
rt_fps_y = int((frame_height-10)*scale)
    
while True:
    # init the real-time FPS counter
    if rt_fps_count == 0:
        rt_fps_time = cv2.getTickCount()

    #if cap.grab():
    if True:
        frame_count = frame_count + 1
        #flag, image = cap.retrieve()
        flag, image = cap.read()
        if not flag:
            break
        else:
            image = cv2.resize(image,(0,0), fx=scale, fy=scale) 
            output = image.copy()
            
            # detect circles in the image
            gray1 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.medianBlur(gray1,5)
            circles = cv2.HoughCircles(gray2, cv2.HOUGH_GRADIENT, 1.5 , 100, minRadius=circle_minRadius,maxRadius=circle_maxRadius)

            circle_list = []
            bbox_list = []
            card_list = []
            
            # ensure at least some circles were found
            if circles is not None:
                # convert the (x, y) coordinates and radius of the circles to integers
                circles = np.round(circles[0, :]).astype("int")
                # loop over the (x, y) coordinates and radius of the circles
                for (cx, cy, r) in circles:
                    # draw the circle in the output image, then draw a rectangle
                    # corresponding to the center of the circle
                    cv2.circle(output, (cx, cy), r, (0, 255, 0), 2)
                    #cv2.rectangle(output, (cx - 5, cy - 5), (cx + 5, cy + 5), (0, 128, 255), -1)

                    # extract ROI for card
                    y1 = (cy-r-b)
                    y2 = (cy+r+b)
                    x1 = (cx-r-b)
                    x2 = (cx+r+b)
                    roi = output[ y1:y2, x1:x2, : ]
                    cv2.rectangle(output, (x1,y1), (x2,y2), (0, 0, 255), 2)
                    
                    try:
                        # dobble pre-processing
                        card_img = cv2.resize(roi,(224,224),interpolation=cv2.INTER_CUBIC)
                        card_img = cv2.cvtColor(card_img, cv2.COLOR_BGR2RGB)
                        card_img = card_img*input_scale
                        card_img = card_img.astype(np.int8)
                        #cv2.imshow('card_img',card_img)
                        card_x = []
                        card_x.append( card_img )
                        card_x = np.array(card_x)

                        # dobble model execution
                        #card_y = model.predict(card_x)

                        """ Prepare input/output buffers """
                        #print("[INFO] process - prep input buffer ")
                        inputData = []
                        inputData.append(np.empty((inputShape),dtype=np.int8,order='C'))
                        inputImage = inputData[0]
                        inputImage[0,...] = card_img

                        #print("[INFO] process - prep output buffer ")
                        outputData = []
                        outputData.append(np.empty((outputShape),dtype=np.int8,order='C'))

                        """ Execute model on DPU """
                        #print("[INFO] process - execute ")
                        job_id = dpu.execute_async( inputData, outputData )
                        dpu.wait(job_id)

                        # dobble post-processing
                        OutputData = outputData[0].reshape(1,58)
                        card_y = np.reshape( OutputData, (-1,58) )
                        card_id  = np.argmax(card_y[0])

                        cv2.putText(output,str(card_id),(x1,y1-b),text_fontType,text_fontSize,text_color,text_lineSize,text_lineType)
                        
                        # Add ROI to card/bbox lists
                        if card_id > 0:
                            circle_list.append((cx,cy,r))
                            bbox_list.append((x1,y1,x2,y2))
                            card_list.append(card_id)

                            if displayReference:
                                reference_img = train1_X[card_id-1]
                                reference_shape = reference_img.shape
                                reference_x = reference_shape[0]
                                reference_y = reference_shape[1]
                                output[y1:y1+reference_y,x1:x1+reference_x,:] = reference_img
                        
                    except:
                        print("ERROR : Exception occured during dobble classification ...")

                         
            if len(card_list) == 1:
                matching_text = ("[%04d] %02d"%(frame_count,card_list[0]))
                print(matching_text)
                
            if len(card_list) > 1:
                #print(card_list)
                matching_text = ("[%04d]"%(frame_count))
                for card_pair in itertools.combinations(card_list,2):
                    #print("\t",card_pair)
                    card1_mapping = mapping[card_pair[0]]
                    card2_mapping = mapping[card_pair[1]]
                    symbol_ids = np.intersect1d(card1_mapping,card2_mapping)
                    #print("\t",symbol_ids)
                    symbol_id = symbol_ids[0]
                    symbol_label = symbols[symbol_id]
                    #print("\t",symbol_id," => ",symbol_label)
                    matching_text = matching_text + (" %02d,%02d=%s"%(card_pair[0],card_pair[1],symbol_label) )
                print(matching_text)
                cv2.putText(output,matching_text,(matching_x,matching_y),text_fontType,text_fontSize,text_color,text_lineSize,text_lineType)                

            # display real-time FPS counter (if valid)
            if rt_fps_valid == True:
                cv2.putText(output,rt_fps_message, (rt_fps_x,rt_fps_y),text_fontType,text_fontSize,text_color,text_lineSize,text_lineType)
            
            # show the output image
            #img1 = np.hstack([image, output])
            #img2 = np.hstack([cv2.merge([gray1,gray1,gray1]), cv2.merge([gray2,gray2,gray2])])
            #cv2.imshow("dobble detection", np.vstack([img1,img2]))
            cv2.imshow("Dobble Classification", output)

    if step == True:
        key = cv2.waitKey(0)
    elif pause == True:
        key = cv2.waitKey(0)
    else:
        key = cv2.waitKey(10)

    #print(key)
    
    if key == 119 or captureAll == True: # 'w'
        for i in range(0,len(card_list)):
            #print("circle_list[",i,"]=",circle_list[i])
            #print("bbox_list[",i,"]=",bbox_list[i])
            #print("card_list[",i,"]=",card_list[i])
            card_id = card_list[i]
            card_title = "card"+str(card_id)
            bbox = bbox_list[i]
            card_img = image[ bbox[1]:bbox[3], bbox[0]:bbox[2] ]
            #cv2.imshow( card_title, card_img )
            #timestr = datetime.now().strftime("%y_%b_%d_%H_%M_%S_%f")
            #filename = timestr+ "_" + card_title + ".tif"
            filename = ("frame%04d_object%d_card%02d.tif"%(frame_count,i,card_id))
            
            print("Capturing ",filename," ...")
            cv2.imwrite(os.path.join(output_dir,filename),card_img)
       
    if key == 115: # 's'
        step = True    
    
    if key == 112: # 'p'
        pause = not pause

    if key == 99: # 'c'
        step = False
        pause = False

    if key == 27:
        break

    # Update the FPS counter
    #fps.update()

    # Update the real-time FPS counter
    rt_fps_count = rt_fps_count + 1
    if rt_fps_count == 10:
        t = (cv2.getTickCount() - rt_fps_time)/cv2.getTickFrequency()
        rt_fps_valid = 1
        rt_fps = 10.0/t
        rt_fps_message = "FPS: {0:.2f}".format(rt_fps)
        #print("[INFO] ",rt_fps_message)
        rt_fps_count = 0



# Stop the timer and display FPS information
#fps.stop()
#print("[INFO] elapsed time: {:.2f}".format(fps.elapsed()))
#print("[INFO] elapsed FPS: {:.2f}".format(fps.fps()))

# Stop the dobble classifier
del dpu

# Cleanup
cv2.destroyAllWindows()
