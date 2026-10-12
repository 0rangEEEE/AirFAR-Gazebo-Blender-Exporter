# 常见故障与 ROS 命令速查

适用于 Ubuntu 20.04 + ROS Noetic + Gazebo Classic 11 + Air-FAR。默认 ROS master 已经启动。

## A. 导入与 Gazebo

- `mkdir -p` 才是正确写法，`kdir -p` 为拼写错误。
- 安装器 `--workspace` 必须指向真实的 `aerial_autonomy_development_environment` 工作区。
- Blender 中的颜色采用 Principled BSDF Base Color；新版本在 `model.sdf` 中给各 `<visual>` 分配 `<diffuse>`。
- Gazebo 报 `bind: Address already in use`，往往是旧 `gzserver` 占用了端口 11345。先检查并从原 roslaunch 终端按 Ctrl+C 结束；`killall` 仅在确认可安全清理时使用。

```bash
MAP=maze
ls -lh "$HOME/.gazebo/models/$MAP/model.sdf"
pgrep -af 'gzserver|gzclient'
```

## B. ROS 节点、位置、感知

```bash
source /opt/ros/noetic/setup.bash

echo '===== 节点 ====='
rosnode list | grep -E 'airfar_planner|localPlanner|pathFollower|vehicleSimulator'

echo '===== 出生点参数 ====='
rosparam get /vehicleSimulator/vehicleX
rosparam get /vehicleSimulator/vehicleY
rosparam get /vehicleSimulator/vehicleZ
rosparam get /vehicleSimulator/vehicleYaw

echo '===== 无人机实时位置 ====='
timeout 5s rostopic echo -n 1 /state_estimation/pose/pose/position

echo '===== 雷达坐标系和频率 ====='
timeout 5s rostopic echo -n 1 /registered_scan/header
timeout 6s rostopic hz /registered_scan

echo '===== 仿真时钟 ====='
timeout 5s rostopic hz /clock
```

## C. 全局航点 → 局部规划 → 跟踪控制

```bash
source /opt/ros/noetic/setup.bash

rostopic info /goal
rostopic info /way_point
timeout 6s rostopic hz /way_point
rostopic info /path
timeout 6s rostopic hz /path
rostopic info /attitude_control
rostopic info /overall_map
rosparam get /airfar_planner/sensor_range
```

**解释：** `/goal` 的发布者消息类型要与接收者一致（`PointStamped` 不等于 `PoseStamped`）；`/way_point` 是 Air-FAR 的引导航点，`/path` 是 LocalPlanner 的局部路径，`/attitude_control` 是 PathFollower 控制输出。GlobalGraph 图边不是实际飞行轨迹。`/overall_map` 的预览点云被 RViz 看到，不等于规划器必然读取了全局先验；需要检查订阅者。

## D. 飞一会就停止

如果 `/clock`、激光点云和 ROS 节点仍活跃，但规划日志出现 `no reachable nav node found`、`FAIL TO REACH GOAL`，通常是该目标的导航任务失败后停止；不是 Gazebo 进程死机。重新给一个连通的近目标可能恢复。不要仅凭复杂迷宫能飞而简单路口不能飞，断言雷达感知范围或地图结构的唯一原因。

## E. 其他警告

`TF_REPEATED_DATA` 不自动证明导致飞行失败；`SearchKNN failed` 是图构建近邻查询的问题，需要独立记录排查。局部贴墙也属于 LocalPlanner/PathFollower 的规划与跟踪问题，不属于材质导出故障。
