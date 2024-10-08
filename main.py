import cv2
import os
import numpy as np
import sys
import open3d as o3d

from bundle_adjustment import bundle_adjustment
from plot_utils import viz_3d, viz_3d_matplotlib, draw_epipolar_lines

######################### Path Variables ##################################################
curr_dir_path = os.getcwd()
print(curr_dir_path)
images_dir = os.path.join(curr_dir_path, "data/images/observatory")
calibration_file_dir = os.path.join(curr_dir_path, "data/calibration")
calibration_file = os.path.join(calibration_file_dir, "cameras.txt")
images_info_file = os.path.join(calibration_file_dir, "images.txt")
###########################################################################################

def count_camera_id_images_num(camera_images_info):
    tmp = [0, 0, 0, 0]
    for k, v in camera_images_info.items():
        tmp[v["camera_id"]] += 1
    print(tmp)

def get_camera_intrinsic(file_path):
    # Camera list with one line of data per camera:
    # CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[fx, fy, cx, cy]
    camera_intrinsic_dict = {}

    with open(file_path, 'r') as file:
        for line in file:
            if (line[0] != "#"):
                info = line.strip().split(" ")
                camera_intrinsic_dict[int(info[0])] = {
                    "camera_id": int(info[0]),
                    "model": info[1],
                    "width": int(info[2]),
                    "height": int(info[3]),
                    "fx": float(info[4]),
                    "fy": float(info[5]),
                    "cx": float(info[6]),
                    "cy": float(info[7]),
                    "k":  [[float(info[4]), 0, float(info[6])], [0, float(info[5]), float(info[7])], [0, 0, 1]]
                }
    
    # print(camera_intrinsic_dict)
    return camera_intrinsic_dict

def get_camera_images_info(file_path):
    # Image list with two lines of data per image:
    # IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
    # POINTS2D[] as (X, Y, POINT3D_ID)
    camera_images_info_dict = {}

    with open(file_path, 'r') as file:
        # 38 0.599829 0.420167 0.369213 -0.572142 5.64051 7.38378 14.2108 0 dslr_images_undistorted/DSC_0323.JPG
        for line in file:
            if (line[0] != "#" and line[-4:-1] == "JPG"):
                info = line.strip().split(" ")
                name = info[9].split("/")[1]
                camera_images_info_dict[name] = {
                    "image_id": int(info[0]),
                    "qw": float(info[1]),
                    "qx": float(info[2]),
                    "qy": float(info[3]),
                    "qz": float(info[4]),
                    "tx": float(info[5]),
                    "ty": float(info[6]),
                    "tz": float(info[7]),
                    "camera_id": int(info[8]),
                    "image_name": info[9]
                }

    # print(camera_images_info_dict)
    return camera_images_info_dict

def get_camera_intrinsic_params():
    K = []
    with open(calibration_file_dir + '/cameras.txt') as f:
        lines = f.readlines()
        calib_info = [float(val) for val in lines[0].split(' ')]
        row1 = [calib_info[0], calib_info[1], calib_info[2]]
        row2 = [calib_info[3], calib_info[4], calib_info[5]]
        row3 = [calib_info[6], calib_info[7], calib_info[8]]

        K.append(row1)
        K.append(row2)
        K.append(row3)
    
    return K

def get_pinhole_intrinsic_params(): # Use this.
    K = []
    with open(calibration_file_dir + '/camera_observatory.txt') as f:
        lines = f.readlines()
        calib_info = [float(val) for val in lines[0].split(' ')]
        row1 = [calib_info[0], 0, calib_info[2]]
        row2 = [0, calib_info[1], calib_info[3]]
        row3 = [0, 0, 1]

        K.append(row1)
        K.append(row2)
        K.append(row3)
    
    return K

def rep_error_fn(opt_variables, points_2d, num_pts):
    P = opt_variables[0:12].reshape(3,4)
    point_3d = opt_variables[12:].reshape((num_pts, 4))

    rep_error = []

    for idx, pt_3d in enumerate(point_3d):
        pt_2d = np.array([points_2d[0][idx], points_2d[1][idx]])

        reprojected_pt = np.matmul(P, pt_3d) # Transform from 3d to 2d, z != 1
        reprojected_pt /= reprojected_pt[2] # Transform from 3d to 2d, z == 1

        # print("Reprojection Error \n" + str(pt_2d - reprojected_pt[0:2]))
        rep_error.append(pt_2d - reprojected_pt[0:2]) # Compared with the GT

    return rep_error


if __name__ == "__main__":
    # Variables
    iter = 0
    prev_img = None
    prev_kp = None
    prev_desc = None
    camera_intrinsic_info = get_camera_intrinsic(calibration_file)
    camera_images_info = get_camera_images_info(images_info_file)

    count_camera_id_images_num(camera_images_info)
    chosen_id = 1 # Chosen camera id.
    bounds = [0, 3]
    set_bundle_adjustment = False

    # K = np.array(get_pinhole_intrinsic_params(), dtype=np.float)
    K = camera_intrinsic_info[chosen_id]["k"]
    R_t_0 = np.array([[1,0,0,0], [0,1,0,0], [0,0,1,0]])
    R_t_1 = np.empty((3,4))
    P1 = np.matmul(K, R_t_0)
    P2 = np.empty((3,4))
    pts_4d = []
    X = np.array([])
    Y = np.array([])
    Z = np.array([])
    rep_error_list = []

    for filename in sorted(os.listdir(images_dir))[bounds[0]:bounds[1]]:
        if (camera_images_info[filename]["camera_id"] != chosen_id):
            continue

        print(f"Iter: {iter}, Filename: {filename}")
        
        file = os.path.join(images_dir, filename)
        img = cv2.imread(file, 0) # Use grayscale.
        # img = cv2.imread(file)
        # cv2.imwrite("output_image.png", img)

        resized_img = img
        sift = cv2.SIFT_create()
        kp, desc = sift.detectAndCompute(resized_img, None) # get Keypoints (pts), Descriptors (vectors)
        # img_with_kp = cv2.drawKeypoints(img, kp, None)
        # cv2.imwrite("output_image.png", img_with_kp)

        if iter == 0:
            prev_img = resized_img
            prev_kp = kp
            prev_desc = desc
        else:
            # FLANN parameters
            FLANN_INDEX_KDTREE = 1
            index_params = dict(algorithm = FLANN_INDEX_KDTREE, trees = 5)
            search_params = dict(checks=100)
            flann = cv2.FlannBasedMatcher(index_params, search_params)
            matches = flann.knnMatch(prev_desc, desc, k=2) # Matching.
            good = []
            pts1 = []
            pts2 = []
            # ratio test as per Lowe's paper
            for i,(m, n) in enumerate(matches):
                if m.distance < 0.7*n.distance:
                    good.append(m)
                    pts1.append(prev_kp[m.queryIdx].pt)
                    pts2.append(kp[m.trainIdx].pt)
                    
            pts1 = np.array(pts1) # Good points in prev.
            pts2 = np.array(pts2) # Good points in curr.
            F, mask = cv2.findFundamentalMat(pts1, pts2, cv2.FM_RANSAC) # Find the fundamental matrix.
            print("The fundamental matrix \n" + str(F))

            # We select only inlier points
            pts1 = pts1[mask.ravel()==1] # flatten by view.
            pts2 = pts2[mask.ravel()==1] # flatten by view.

            # draw_epipolar_lines(pts1, pts2, prev_img, resized_img, F)
            E = np.matmul(np.matmul(np.transpose(K), F), K)

            print("The new essential matrix is \n" + str(E))

            retval, R, t, mask = cv2.recoverPose(E, pts1, pts2, cameraMatrix=np.array(K))
            
            print("I+0 \n" + str(R_t_0))

            print("Mullllllllllllll \n" + str(np.matmul(R, R_t_0[:3,:3])))

            R_t_1[:3,:3] = np.matmul(R, R_t_0[:3,:3]) # Camera extrinsic: rotation.
            R_t_1[:3, 3] = R_t_0[:3, 3] + np.matmul(R_t_0[:3,:3], t.ravel()) # Camera extrinsic: translation.

            print("The R_t_0 \n" + str(R_t_0))
            print("The R_t_1 \n" + str(R_t_1))

            P2 = np.matmul(K, R_t_1)

            print("The projection matrix 1 \n" + str(P1))
            print("The projection matrix 2 \n" + str(P2))

            pts1 = np.transpose(pts1)
            pts2 = np.transpose(pts2)

            print("Shape pts 1\n" + str(pts1.shape))

            points_3d = cv2.triangulatePoints(P1, P2, pts1, pts2) # Triangulation: reconstructing 3D points from two 2D projections.
            points_3d /= points_3d[3]

            if (set_bundle_adjustment): # Very long.
                P2, points_3D = bundle_adjustment(points_3d, pts2, resized_img, P2)
            opt_variables = np.hstack((P2.ravel(), points_3d.ravel(order="F")))
            num_points = len(pts2[0])
            rep_error_list.append(rep_error_fn(opt_variables, pts2, num_points))

            X = np.concatenate((X, points_3d[0]))
            Y = np.concatenate((Y, points_3d[1]))
            Z = np.concatenate((Z, points_3d[2]))

            R_t_0 = np.copy(R_t_1)
            P1 = np.copy(P2)
            prev_img = resized_img
            prev_kp = kp
            prev_desc = desc

        iter = iter + 1

    # pts_4d.append(X)
    # pts_4d.append(Y)
    # pts_4d.append(Z)
    pts_4d = np.column_stack((X, Y, Z)).astype(np.float64)
    np.save('array.npy', pts_4d)

    viz_3d(pts_4d)