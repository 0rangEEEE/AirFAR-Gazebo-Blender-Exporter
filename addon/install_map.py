#!/usr/bin/env python3
"""Install exported Blender map into user's Gazebo Classic 11 / vehicle_simulator workspace."""
import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET


def install(bundle, workspace):
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    name = manifest['map_name']
    # The installer never executes content from the bundle.
    if not name or not name.replace('_','').isalnum() or not name[0].isalpha():
        raise ValueError('Invalid map name')
    ws = workspace.expanduser().resolve()
    package = ws / 'src' / 'vehicle_simulator'
    if not (package / 'launch' / 'system_gazebo.launch').is_file():
        raise FileNotFoundError('Missing vehicle_simulator/launch/system_gazebo.launch in ' + str(package))
    src_model = bundle / 'model' / name
    src_world = bundle / 'world' / (name+'.world')
    src_launch = bundle / 'launch' / ('start_'+name+'.launch')
    for f in [src_model/'model.sdf',src_model/'model.config',src_model/'meshes'/'visual.obj',src_model/'preview'/'pointcloud.ply',src_world,src_launch]:
        if not f.is_file():
            raise FileNotFoundError(f)
    dst_model = Path.home()/'.gazebo'/'models'/name
    dst_preview = package/'mesh'/name/'preview'/'pointcloud.ply'
    dst_world = package/'world'/(name+'.world')
    dst_launch = package/'launch'/('start_'+name+'.launch')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backups=[]
    for p in [dst_model,dst_preview,dst_world,dst_launch]:
        if p.exists():
            bak=p.with_name(p.name+'.backup_'+stamp)
            if p.is_dir():
                shutil.copytree(p,bak)
            else:
                shutil.copy2(p,bak)
            backups.append(str(bak))
    dst_model.parent.mkdir(parents=True,exist_ok=True)
    if dst_model.exists():
        shutil.rmtree(dst_model)
    shutil.copytree(src_model,dst_model)
    dst_preview.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src_model/'preview'/'pointcloud.ply',dst_preview)
    dst_world.parent.mkdir(parents=True,exist_ok=True)
    dst_launch.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src_world,dst_world)
    # Install a copy of the REAL simulator launch file with this map and spawn
    # configured.  Suppress its built-in RViz, because the Air-FAR planner
    # launch starts the Air-FAR RViz separately.
    root = ET.parse(package / 'launch' / 'system_gazebo.launch').getroot()
    defaults = {'map_name': name, 'gazebo_gui':'false', 'config':'indoor',
                'vehicleX': str(manifest['spawn']['x']),
                'vehicleY': str(manifest['spawn']['y']),
                'vehicleZ': str(manifest['spawn']['z']),
                'vehicleYaw': str(manifest['spawn']['yaw_radians'])}
    defined = set()
    for arg in root.findall('arg'):
        k = arg.get('name')
        if k in defaults:
            arg.set('default', defaults[k])
            defined.add(k)
    if 'map_name' not in defined or not all(k in defined for k in ('vehicleX','vehicleY','vehicleZ','vehicleYaw')):
        raise ValueError('The local system_gazebo.launch does not expose required spawn arguments')
    for parent in root.iter():
        for child in list(parent):
            if child.tag == 'node' and child.get('pkg') == 'rviz':
                parent.remove(child)
    ET.ElementTree(root).write(dst_launch, encoding='utf-8', xml_declaration=True)
    print('[OK] Model:',dst_model)
    print('[OK] RViz full static map:',dst_preview)
    print('[OK] World:',dst_world)
    print('[OK] Launch:',dst_launch)
    print('[OK] Drone spawn:',manifest['spawn'])
    for p in backups:
        print('[BACKUP]',p)
    print('\nRUN SIMULATOR:')
    print('source /opt/ros/noetic/setup.bash')
    print('source '+str(ws/'devel'/'setup.bash'))
    print('roslaunch vehicle_simulator start_'+name+'.launch')
    print('\nRUN AIR-FAR (another terminal):')
    print('source /opt/ros/noetic/setup.bash')
    print('source '+str(ws/'devel'/'setup.bash'))
    print('source '+str(Path.home()/'airfar_ws'/'Air-FAR'/'devel'/'setup.bash'))
    print('roslaunch airfar_planner airfar.launch config_file:=default rviz_file:=airfar_tunnel')
    print('\nIf Gazebo cannot find model, verify ~/.gazebo/models and GAZEBO_MODEL_PATH.')


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--workspace',type=Path,default=Path.home()/'airfar_ws'/'aerial_autonomy_development_environment')
    a.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parent)
    args=a.parse_args()
    install(args.bundle.resolve(),args.workspace)

if __name__=='__main__':
    main()
