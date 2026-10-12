# AirFAR Gazebo Blender Exporter — English quick guide

> This is a community-developed Blender add-on, **not an official project by the Air-FAR authors**.

**Purpose:** export static Blender 4.2+ scenes into Gazebo Classic 11 models and ROS Noetic / Air-FAR simulation bundles. Solid-color Principled BSDF Base Color is converted into per-material meshes with explicit SDF colors. Exports collision meshes or boxes, a `UAV_SPAWN` pose, `.world`, static preview PLY and Air-FAR launch files.

## Requirements

Blender 4.2+, Ubuntu 20.04, ROS Noetic, Gazebo Classic 11, and a built [Air-FAR](https://github.com/Bottle101/Air-FAR) + [aerial autonomy development environment](https://github.com/Bottle101/aerial_autonomy_development_environment) workspace.

## Try the included `maze` maze first

The repository includes an editable [Blender source scene](examples/maze/maze.blend) and a ready-to-install [Gazebo map bundle](examples/maze/maze_gazebo_bundle.zip). Copy it to the VM's `~/下载/` folder and follow the [complete `maze` walkthrough](examples/maze/README.md). It includes both simulator and Air-FAR launches, RViz **Goalpoint3D** goal-setting and ROS diagnosis commands. Blender is not required to run this example.

## Install / export

1. Download `dist/AirFAR_Gazebo_Blender_Addon_v0_3.zip` and install **from disk** in Blender (do not unzip it).
2. In Blender, add an Empty named `UAV_SPAWN` and prepare walls/floor with Principled BSDF colors. Press `N` → **Gazebo** → **One-click Export for Gazebo**.
3. Copy `<map>_gazebo_bundle.zip` to Ubuntu `~/下载/`.

## Ubuntu (example map `maze`)

```bash
MAP=maze
WS="$HOME/airfar_ws/aerial_autonomy_development_environment"
IMPORT="$HOME/airfar_map_import/${MAP}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$IMPORT"
unzip -o "$HOME/下载/${MAP}_gazebo_bundle.zip" -d "$IMPORT"
cd "$IMPORT" || exit 1
python3 install_map.py --workspace "$WS"
```

**Terminal 1:**

```bash
source /opt/ros/noetic/setup.bash
source "$HOME/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash"
roslaunch vehicle_simulator start_maze.launch gazebo_gui:=true
```

**Terminal 2:**

```bash
source /opt/ros/noetic/setup.bash
source "$HOME/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash"
source "$HOME/airfar_ws/Air-FAR/devel/setup.bash"
roslaunch airfar_planner airfar.launch config_file:=default rviz_file:=airfar_tunnel
```

In RViz use **Goalpoint3D** for Air-FAR navigation goals.

## Limitations

Static environment mesh export only; simple colors are supported, Blender procedural/PBR rendering equivalence is not. The generated full-map point cloud is for **visualization only**, not a substitute for online sensing. Planning / collision avoidance quality is not guaranteed by the exporter. EGO/FAST-Planner need separate launch, sensor and planner adapters; the underlying Gazebo `model.sdf` may be reused.

Full Chinese instructions: [docs/USAGE_ZH.md](docs/USAGE_ZH.md).
