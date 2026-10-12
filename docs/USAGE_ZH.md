# 中文使用教程（v0.3）

## 1. 项目功能与边界

本项目是一套 **Blender → Gazebo Classic 11 → ROS Noetic / Air-FAR** 静态地图导出工具。Blender 中的墙体、地板、纯色材质、碰撞代理和无人机初始位姿可一键封装为标准 Gazebo 模型、World、预览点云及 Air-FAR 启动适配文件。当前 Air-FAR 启动与安装适配依赖 `vehicle_simulator`，不要误认为任意规划器都可即插即用。

## 2. 不用 Blender，直接跑通 `maze` 示例

仓库附带可编辑的 [`maze.blend`](../examples/maze/maze.blend) 和已导出的迷宫地图压缩包：[`examples/maze/maze_gazebo_bundle.zip`](../examples/maze/maze_gazebo_bundle.zip)。如果你想先确认 Gazebo → Air-FAR 的环境正常，**不必自行建模**。

请先阅读 [maze 快速上手教程](../examples/maze/README.md)：包括安装、两个终端启动、在 RViz 中用 `Goalpoint3D` 标点飞行、以及诊断命令。示例初始出生点在 `(-2.865, -8.800, 3.691)` m，并非世界原点。

## 3. Blender 准备

1. 建立三维网格，约定 1 BU = 1 m，坐标 Z 向上。导出程序读取物体的世界变换；物体不用全部移到世界原点。
2. 纯色材质请使用 **Principled BSDF（原理化 BSDF）→ Base Color（基础色）**，不必改成“自发光”。给墙体和地板分配不同材质。
3. 删除不必要的重合面，使用“按距离合并”时注意阈值；检查法线、重叠地板、封闭碰撞体。
4. 新建 Empty（空物体），**严格命名为 `UAV_SPAWN`**。按世界坐标放在安全空域，旋转 Z 轴设置初始 yaw，避免出生点位于障碍内。
5. 可选碰撞代理：`COL_BOX_...` 为 Box，`COL_...` 为 Mesh；只用于碰撞。没有碰撞代理时，插件把可视网格作为碰撞网格，复杂迷宫可能导致 STL 面数高、性能差。
6. 不希望导出的对象按扩展约定使用 `NOEXPORT_...` 命名，并在导出前确认场景对象状态。
7. 3D Viewport 按 `N` → **Gazebo / Air-FAR Gazebo Map**；设置 Map name、Output folder，勾选 Create ZIP；按 **One-click Export for Gazebo**。

### v0.3 为什么修好黑色墙体？

旧版主要由 Gazebo 从单个 `visual.obj` + `visual.mtl` 间接读取材质。现版本读取 Principled BSDF 的 Base Color，把各材质对应三角面分别输出至 `visual_mat_XXX.obj`，在 `model.sdf` 的每个 `<visual>` 下设置 `<ambient>`、`<diffuse>` 和低幅度 `<emissive>`。不同材质不再仅依赖 OBJ/MTL 的解析结果。此方式适合**纯色**场景；复杂纹理节点/透明/反射等不保证等效。

## 4. 区分两个 ZIP

- `AirFAR_Gazebo_Blender_Addon_v0_3.zip`：这是 **Blender 插件**，从 GitHub 下载并在 Blender 内“从磁盘安装”，不要提前解压后放进 Ubuntu。
- `maze_gazebo_bundle.zip`：这是 **Blender 导出的地图包**，放到 Ubuntu `~/下载/`，解压并运行内部的 `install_map.py`。

## 5. Ubuntu 安装地图

将 `MAP=maze` 替换成 Blender 的 Map name：

```bash
MAP=maze
WS="$HOME/airfar_ws/aerial_autonomy_development_environment"
ZIP="$HOME/下载/${MAP}_gazebo_bundle.zip"
IMPORT="$HOME/airfar_map_import/${MAP}_$(date +%Y%m%d_%H%M%S)"

mkdir -p "$IMPORT"
unzip -o "$ZIP" -d "$IMPORT"
cd "$IMPORT" || exit 1
ls -lh
python3 install_map.py --workspace "$WS"
```

使用带时间戳的解压目录避免旧 ZIP 残留文件的影响。安装器会为已存在的部署目标创建时间戳备份，但仍应自己备份重要改动。

### 安装结果

```text
~/.gazebo/models/maze/model.sdf
~/airfar_ws/aerial_autonomy_development_environment/src/vehicle_simulator/world/maze.world
~/airfar_ws/aerial_autonomy_development_environment/src/vehicle_simulator/launch/start_maze.launch
~/airfar_ws/aerial_autonomy_development_environment/src/vehicle_simulator/mesh/maze/preview/pointcloud.ply
```

## 6. 启动（两个终端）

终端 1（仿真环境）：

```bash
MAP=maze
source /opt/ros/noetic/setup.bash
source "$HOME/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash"
roslaunch vehicle_simulator "start_${MAP}.launch" gazebo_gui:=true
```

终端 2（Air-FAR 规划及 RViz）：

```bash
source /opt/ros/noetic/setup.bash
source "$HOME/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash"
source "$HOME/airfar_ws/Air-FAR/devel/setup.bash"
roslaunch airfar_planner airfar.launch config_file:=default rviz_file:=airfar_tunnel
```

正常情况下：Gazebo 加载 Blender 地图，RGB / LiDAR 仿真节点发布传感器数据；RViz 显示在线构建的导航图；使用 **Goalpoint3D** 标记全局目标，Air-FAR 发布 `/way_point`，本地 `localPlanner` 产生 `/path`，`pathFollower` 输出 `/attitude_control`。注意 `Goalpoint3D` 和 `Waypoint3D` 目的不同。

## 7. 推荐的工程验收

检查 Gazebo 颜色、所有墙体的碰撞边界、起始位置是否安全、激光点云是否来自真实场景、导航图是否逐步扩展、局部路径是否持续输出。局部路径贴墙或远目标导航失败属于规划/跟踪层问题，不等于 Blender 资源导出失败。

完整命令见 [故障排查](TROUBLESHOOTING_ZH.md)。

## 8. v0.3 范围外功能

暂不宣称：复杂图片贴图和程序化 PBR 材质的完整复刻、动态障碍物/动画、无人机碰撞后的真实动力学响应、EGO 或 FAST-Planner 的一键安装及对任意世界尺寸的自动感知配置。
