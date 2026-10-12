# maze — Blender / Gazebo / Air-FAR 迷宫示例

[项目首页](../../README.md) · [完整中文使用教程](../../docs/USAGE_ZH.md) · [故障排查](../../docs/TROUBLESHOOTING_ZH.md)

![RViz 中的在线导航图](../../docs/images/maze_rviz_graph.png)

示例提供可编辑的 Blender 三维源工程及其 Gazebo Classic 导出包，用于复现自定义静态地图在 ROS Noetic / Air-FAR 中的加载、感知与目标导航流程。上游 Air-FAR 和仿真工作区需单独安装、编译。

## 文件

| 文件 | 用途 |
|---|---|
| [`maze.blend`](maze.blend) | 可编辑 Blender 迷宫工程；使用 Blender 4.2+ 打开 |
| [`maze_gazebo_bundle.zip`](maze_gazebo_bundle.zip) | 可直接部署的 Gazebo + Air-FAR 导出地图 |
| `../../docs/images/maze_rviz_graph.png` | RViz 在线全局拓扑图演示截图 |
| `../../docs/images/maze_return_path.png` | 已探索区域返航路线演示截图 |

导出包内部的地图标识（`manifest.json`、`model/maze/`、`world/maze.world`、`start_maze.launch`）统一为 **`maze`**。

## A. 直接运行导出地图（无需 Blender）

先将 `maze_gazebo_bundle.zip` 放到 Ubuntu `~/下载/`，再执行：

```bash
MAP=maze
WS="$HOME/airfar_ws/aerial_autonomy_development_environment"
IMPORT="$HOME/airfar_map_import/${MAP}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$IMPORT"
unzip -o "$HOME/下载/${MAP}_gazebo_bundle.zip" -d "$IMPORT"
cd "$IMPORT" || exit 1
python3 install_map.py --workspace "$WS"
```

**终端 1：Gazebo / vehicle_simulator**

```bash
source /opt/ros/noetic/setup.bash
source "$HOME/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash"
roslaunch vehicle_simulator start_maze.launch gazebo_gui:=false
```

**终端 2：Air-FAR / RViz**

```bash
source /opt/ros/noetic/setup.bash
source "$HOME/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash"
source "$HOME/airfar_ws/Air-FAR/devel/setup.bash"
roslaunch airfar_planner airfar.launch \
  config_file:=default rviz_file:=airfar_tunnel
```

在 RViz 中用 **Goalpoint3D** 设置全局目标；`Waypoint3D` 属于不同的局部航点接口。

![已探索走廊的返航规划](../../docs/images/maze_return_path.png)

## B. 修改 Blender 工程并重新导出

使用 Blender 4.2+ 打开 `maze.blend`，安装 [`dist/AirFAR_Gazebo_Blender_Addon_v0_3.zip`](../../dist/AirFAR_Gazebo_Blender_Addon_v0_3.zip)。在三维视图侧栏 Gazebo 面板：

1. 检查场景几何、纯色材质、`UAV_SPAWN` 的位置及航向。
2. 确认 **Map name = `maze`**，选择 Output folder，启用 Create ZIP。
3. 点击 **One-click Export for Gazebo**，生成 `maze_gazebo_bundle.zip`。
4. 将新生成的 ZIP 依照 **A** 部分安装。其几何、出生点及导出警告可能随工程修改而变化。

`maze.blend` 的导出地图名设为 `maze`；导出前需在插件面板确认该值。

## 示例参数与限制

| 属性 | 当前随附地图包 |
|---|---|
| 出生位置 | (-2.8654, -8.8004, 3.6912) m |
| 出生偏航角 | 0 rad |
| 可视网格 | 22,105 个三角面，两组纯色材质 |
| 碰撞网格 | 一组，约 22,125 个三角面 |
| 完整地图预览点云 | 250,000 点，仅供显示 |

导出记录提示：场景没有独立的 `COL_` 简化碰撞代理，使用可视几何作为碰撞体；还存在若干跳过退化面的警告。这些内容应在后续场景优化中检查。

完整点云 `preview/pointcloud.ply` **并非在线 LiDAR 观测**。全局拓扑图、路径规划和飞行安全受在线传感器、规划器与跟踪器影响，示例不构成无碰撞或任意目标可达的保证。

**素材权利：** Blender 场景及地图文件的公开再分发须具有相应授权；插件源码的 MIT 许可不当然覆盖第三方场景资产。详见 [场景素材声明](ASSET_NOTICE.md)。
