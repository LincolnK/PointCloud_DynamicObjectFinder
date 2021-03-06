#!/usr/bin/env python2

import rospy
import time

import numpy as np
import cv2

from sensor_msgs.msg import PointCloud2
from sensor_msgs import point_cloud2

from geometry_msgs.msg import Point

from nav_msgs.msg import GridCells

from sensor_msgs.msg import Image

from cv_bridge import CvBridge

from geometry_msgs.msg import Pose 

PREV_IMG = None
READY = False

PREV_POSITION = [0,0]
CURRENT_POSITION = [0,0]

_SIZE = 350 # size of the image
_RING_MIN = rospy.get_param("/ring_min") # lowest ring that will be scanned
_RING_MAX = rospy.get_param("/ring_max") # highest ring that will
_LIDAR_TOPIC = rospy.get_param("/lidar_topic") # lowest ring that will be scanned
_ODOM_TOPIC = rospy.get_param("/odom_topic") # highest ring that will


original_pub = rospy.Publisher('voxel_data/original', Image, queue_size=1)
noise_pub= rospy.Publisher('voxel_data/noise', Image, queue_size=1)

def position_callback(data):
	global CURRENT_POSITION
	saved_pos = CURRENT_POSITION
	try:
		CURRENT_POSITION[0] = data.position.x
		CURRENT_POSITION[0] = data.position.y
	except:
		CURRENT_POSITION = saved_pos
		rospy.loginfo("Position update error!")

def callback(data):
	global PREV_IMG
	global PREV_POSITION
	global READY
	measured_position = list(CURRENT_POSITION) # we want the measured position to be as close to the time the lidar data was measured as possible. It's possible that the current position could change during this callback
	bridge = CvBridge()
	gen = point_cloud2.read_points(data, field_names = ("x", "y", "ring"))

	voxels = np.zeros((_SIZE, _SIZE, _RING_MAX-_RING_MIN+1), dtype=np.uint8)
	
	lidar_points = [[] for x in xrange(_RING_MIN, _RING_MAX+1)]
	for j in gen:
		if ((j[2] >= _RING_MIN) and (j[2] <= _RING_MAX)):
			if( (abs(j[0]) < 17.5) and (abs(j[1]) < 17.5) ):
				x_voxel = int((j[0]+17.5)*10)
				y_voxel = int((j[1]+17.5)*10)
				ring = int(j[2]-_RING_MIN)
				voxels[x_voxel][y_voxel][ring] = 255
	
	if READY:
		
		y_shift = int((measured_position[0] - PREV_POSITION[0]) * -10)
		x_shift = int((measured_position[1] - PREV_POSITION[1]) * -10)
		shift = np.float32([[1, 0, x_shift],[0,1,y_shift]])
		rows, cols, zeasus = voxels.shape
		shifted_prev_img = cv2.warpAffine(PREV_IMG, shift, (cols, rows))
		
		subtracted_image = cv2.subtract(voxels, shifted_prev_img)
		filtered_image = subtracted_image
		filtered_image = im_3d_filter(subtracted_image)
		
		flat_image = flatten(filtered_image)
		flat_image = cv2.GaussianBlur(flat_image,(3,3),0)
		
		flat_original = flatten(voxels)
		flat_original = cv2.GaussianBlur(flat_original,(3,3),0)
		
		image_message = bridge.cv2_to_imgmsg(flat_image, encoding="passthrough")
		image_message.header.stamp = rospy.Time.now()
		noise_pub.publish(image_message)
		
		image_message = bridge.cv2_to_imgmsg(flat_original, encoding="passthrough")
		image_message.header.stamp = rospy.Time.now()
		original_pub.publish(image_message)
		
		
	PREV_IMG = voxels
	PREV_POSITION = measured_position
	READY = True
		
	
def flatten(image):
	imcopy = np.sum(image, axis=2)
	imcopy = imcopy.astype(np.uint8)
	return imcopy
		
# This funciton will threshold the input image based off of detection_thresh
# output is a binary image of pixles that survive the thresholding
# function also sets pixles in the center to zero
def im_2d_filter(image):
	imcopy = image
	detection_thresh = 250
	imcopy[imcopy > detection_thresh] = 255
	imcopy[imcopy <= detection_thresh] = 0
	imcopycopy = imcopy
	detected_pixels = np.where(imcopy == 255)
	for i in range(len(detected_pixels[0])):
		pixel = [detected_pixels[0][i], detected_pixels[1][i]]
		adjacent_pixels = check_nearby_pixels(pixel, imcopy)
		if(adjacent_pixels < 2):
			imcopycopy[pixel[0]][pixel[1]] = 0
	imcopycopy[171:180,171:180] = 0
	return imcopycopy

# custom 3d filter similar to a gaussian filter that works in three dimensions
def im_3d_filter(image):
	raw_pixels = np.where(image == 255)
	imcopy = np.zeros((_SIZE, _SIZE, _RING_MAX-_RING_MIN+1), dtype=np.uint8)
	
	pixels = []
	# can speed this up by combining the two for loops
	for i in range(len(raw_pixels[0])):
		pixels.append([raw_pixels[0][i], raw_pixels[1][i], raw_pixels[2][i]])
		
	for pixel in pixels:
		adjacent_pixels = check_nearby_pixels(pixel, image)*(85/(_RING_MAX - _RING_MIN + 1))
		if(adjacent_pixels > 255):
			#rospy.loginfo("Greater than 255 detected!")
			adjacent_pixels = 255
		imcopy[pixel[0]][pixel[1]][pixel[2]] = int(adjacent_pixels)

	return imcopy
		
# returns the number of adjacent 255 pixles in the image to the provided pixel location
def check_nearby_pixels(pixel_location, image):
	i = 0
	x_lower_bound = pixel_location[0] - 1
	if(x_lower_bound < 0):
		x_lower_bound = 0
		
	x_upper_bound = pixel_location[0] + 2
	if(x_upper_bound > (_SIZE)):
		x_upper_bound = _SIZE

	y_lower_bound = pixel_location[1] - 1
	if(y_lower_bound < 0):
		y_lower_bound = 0
		
	y_upper_bound = pixel_location[1] + 2
	if(y_upper_bound > (_SIZE)):
		y_upper_bound = _SIZE
		
	if(len(pixel_location) == 3): # 3d Image
		z_lower_bound = pixel_location[2] - 1
		if(z_lower_bound < 0):
			z_lower_bound = 0
		
		z_upper_bound = pixel_location[2] + 2
		if(z_upper_bound > ((_RING_MAX+1)-_RING_MIN)):
			z_upper_bound = (_RING_MAX+1)-_RING_MIN
		
		pixels = image[x_lower_bound:x_upper_bound, y_lower_bound:y_upper_bound, z_lower_bound:z_upper_bound]
		for pixel in pixels.flatten():
			if pixel == 255:
				i+= 1
	else: # 2d image
		pixels = image[x_lower_bound:x_upper_bound, y_lower_bound:y_upper_bound]
		for pixel in pixels.flatten():
			if pixel == 255:
				i+= 1
			
	return i

def main():
	rospy.init_node('voxelizer', anonymous=False)
	rospy.Subscriber(_LIDAR_TOPIC, PointCloud2, callback)
	rospy.Subscriber(_ODOM_TOPIC, Pose, position_callback)
	rospy.spin()

	
if __name__ == "__main__":
	try:
		main()
	except rospy.ROSInterruptException:
		pass
		
