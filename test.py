import open3d as o3d
import numpy as np

# 创建一些示例点云数据 (Nx3 数组)
points = np.load('array.npy')
# points = np.array([[0, 0, 0],
#                    [1, 0, 0],
#                    [0, 1, 0],
#                    [0, 0, 1]], dtype=np.float64)

# 创建 Open3D 点云对象
pcd = o3d.geometry.PointCloud()

# 将 numpy 数组转换为 Open3D 格式的点云
pcd.points = o3d.utility.Vector3dVector(points)

# Visualize the point cloud
o3d.visualization.draw_geometries([pcd], 
                                    zoom=0.5,
                                    front=[0, 0, -1], 
                                    lookat=[10, 10, 10], 
                                    up=[0, 1, 0])
