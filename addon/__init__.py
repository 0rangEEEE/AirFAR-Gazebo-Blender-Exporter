bl_info = {
    "name": "Air-FAR Gazebo Classic One-click Map Exporter",
    "author": "0rangEEEE",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar (N) > Gazebo",
    "description": "Export Blender static environment with explicit SDF per-material visuals",
    "category": "Import-Export",
}

import bpy
import bisect
import random
import math
import mathutils
import shutil
import struct
import zipfile
import json
import os
import re
import traceback
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom
from bpy.props import StringProperty, BoolProperty


def safe_name(v):
    s = re.sub(r"[^a-zA-Z0-9_]", "_", v.strip().lower())
    if not s or not s[0].isalpha():
        s = "map_" + s
    return s[:64]


def nfmt(v):
    f = float(v)
    if not math.isfinite(f):
        raise ValueError("Geometry contains NaN or Infinity")
    return "%.9g" % (0.0 if abs(f) < 1e-11 else f)


def sub(parent, tag, val=None, **attrib):
    node = ET.SubElement(parent, tag, attrib)
    if val is not None:
        node.text = str(val)
    return node


def xml_to_file(root, filename):
    rough = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    Path(filename).write_bytes(pretty)


def transform_xyz(matrix, v, unit):
    q = matrix @ v
    return (q.x * unit, q.y * unit, q.z * unit)


def actual_mesh(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    if mesh is None:
        raise ValueError("Cannot evaluate mesh: " + obj.name)
    mesh.calc_loop_triangles() if hasattr(mesh, "calc_loop_triangles") else None
    return evaluated, mesh


def material_info(material, tex_dir, warnings):
    if material is None:
        return (0.72, 0.72, 0.72), None
    col = material.diffuse_color
    color = (float(col[0]), float(col[1]), float(col[2]))
    image = None
    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                socket = node.inputs.get('Base Color')
                if socket:
                    color = tuple(float(c) for c in socket.default_value[:3])
                    if socket.is_linked:
                        for link in socket.links:
                            if link.from_node.type == 'TEX_IMAGE' and link.from_node.image:
                                image = link.from_node.image
                                break
        if image is None:
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    image = node.image
                    break
    texture_ref = None
    if image is not None:
        src_path = bpy.path.abspath(image.filepath, library=image.library)
        ext = Path(src_path).suffix.lower() or '.png'
        dest = safe_name(image.name) + ext
        target = tex_dir / dest
        try:
            if src_path and Path(src_path).is_file():
                shutil.copy2(src_path, target)
                texture_ref = "../materials/textures/" + dest
            elif image.packed_file:
                # PNG export of packed image, if supported by its Blender image datablock
                target = tex_dir / (safe_name(image.name) + '.png')
                image.save_render(str(target))
                texture_ref = "../materials/textures/" + target.name
            else:
                warnings.append("Missing texture for material %s: %s" % (material.name, src_path))
        except Exception as exc:
            warnings.append("Cannot copy texture %s: %s" % (image.name, exc))
    return color, texture_ref


def write_obj(objects, depsgraph, dst, tex_dir, unit, warnings):
    obj_path = dst / 'visual.obj'
    mtl_path = dst / 'visual.mtl'
    mat_lines = []
    material_cache = {}
    triangle_count = 0
    verts_start, uv_start, norm_start = 1, 1, 1
    with obj_path.open('w', encoding='utf-8') as outf:
        outf.write('# Generated for Gazebo Classic 11; world coordinates, meters, Z-up\nmtllib visual.mtl\n')
        for obj in objects:
            evaluated, mesh = actual_mesh(obj, depsgraph)
            try:
                if not mesh.vertices or not mesh.loop_triangles:
                    warnings.append("Skipped empty visual mesh " + obj.name)
                    continue
                outf.write('o object_%d\n' % (len(material_cache) + verts_start))
                for vertex in mesh.vertices:
                    p = transform_xyz(obj.matrix_world, vertex.co, unit)
                    outf.write('v %s %s %s\n' % tuple(nfmt(x) for x in p))
                uv_layer = mesh.uv_layers.active
                uv_data = uv_layer.data if uv_layer is not None else None
                flip = obj.matrix_world.determinant() < 0
                normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
                for tri in mesh.loop_triangles:
                    ids = list(tri.vertices)
                    loops = list(tri.loops)
                    if flip:
                        ids.reverse()
                        loops.reverse()
                    mi = mesh.polygons[tri.polygon_index].material_index
                    material = mesh.materials[mi] if mi < len(mesh.materials) else None
                    key = material.name_full if material is not None else '__default__'
                    if key not in material_cache:
                        mat_name = 'mat_%03d' % len(material_cache)
                        material_cache[key] = mat_name
                        color, texture = material_info(material, tex_dir, warnings)
                        mat_lines.extend(['newmtl ' + mat_name,
                                          'Ka 0.15 0.15 0.15',
                                          'Kd %s %s %s' % tuple(nfmt(x) for x in color),
                                          'Ks 0 0 0', 'd 1.0', 'illum 1'])
                        if texture:
                            mat_lines.append('map_Kd ' + texture)
                        mat_lines.append('')
                    outf.write('usemtl ' + material_cache[key] + '\n')
                    normal = normal_matrix @ tri.normal
                    if normal.length_squared < 1e-16:
                        warnings.append('Skipped degenerate face in ' + obj.name)
                        continue
                    normal.normalize()
                    outf.write('vn %s %s %s\n' % tuple(nfmt(a) for a in normal))
                    normal_id = norm_start
                    norm_start += 1
                    if uv_data:
                        for li in loops:
                            uv = uv_data[li].uv
                            outf.write('vt %s %s\n' % (nfmt(uv.x), nfmt(uv.y)))
                        refs = ['%d/%d/%d' % (verts_start + vi, uv_start + j, normal_id) for j, vi in enumerate(ids)]
                        uv_start += 3
                    else:
                        refs = ['%d//%d' % (verts_start + vi, normal_id) for vi in ids]
                    outf.write('f ' + ' '.join(refs) + '\n')
                    triangle_count += 1
                verts_start += len(mesh.vertices)
            finally:
                evaluated.to_mesh_clear()
    mtl_path.write_text('\n'.join(mat_lines) + '\n', encoding='utf-8')
    return triangle_count


def split_visuals_by_material(mesh_dir, warnings):
    """Split OBJ by usemtl and return (obj_filename, material_name, RGB) triples.

    Keep OBJ's global v/vt/vn indices intact by duplicating its shared declarations
    into each new file. This is robust for pure-color meshes and preserves UV data.
    """
    obj_file = mesh_dir / 'visual.obj'
    mtl_file = mesh_dir / 'visual.mtl'
    declarations = []
    groups = {}
    selected = None
    with obj_file.open('r', encoding='utf-8') as source:
        for raw in source:
            line = raw.strip()
            if line.startswith(('v ', 'vt ', 'vn ')):
                declarations.append(line)
            elif line.startswith('usemtl '):
                selected = line.split(maxsplit=1)[1]
                groups.setdefault(selected, [])
            elif line.startswith('f '):
                if selected is None:
                    raise ValueError('Visual OBJ has a face with no assigned material')
                groups[selected].append(line)
    colors = {}
    active = None
    for raw in mtl_file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('newmtl '):
            active = line.split(maxsplit=1)[1]
        elif active is not None and line.startswith('Kd '):
            colors[active] = tuple(float(x) for x in line.split()[1:4])
    for leftover in mesh_dir.glob('visual_mat_*.obj'):
        leftover.unlink()
    visuals = []
    for mat_name, faces in groups.items():
        if not faces:
            continue
        if not re.fullmatch(r'mat_\d{3}', mat_name):
            raise ValueError('Unexpected material id: ' + mat_name)
        if mat_name not in colors:
            raise ValueError('Missing Kd color for: ' + mat_name)
        filename = 'visual_' + mat_name + '.obj'
        output = mesh_dir / filename
        output.write_text('\n'.join([
            '# Per-material visual OBJ for Gazebo Classic',
            'mtllib visual.mtl',
            *declarations,
            'o ' + mat_name,
            'usemtl ' + mat_name,
            *faces,
            ''
        ]), encoding='utf-8')
        visuals.append((filename, mat_name, colors[mat_name]))
        print('[Air-FAR EXPORT MATERIAL]', mat_name, 'faces=', len(faces), 'color=', colors[mat_name])
    if not visuals:
        raise ValueError('Visual OBJ has no material-assigned triangles')
    return visuals


def sample_obj_to_ply(obj_path, ply_path, spacing=0.16, max_points=250000, seed=11):
    vertices = []
    cumulative = []
    triangles = []
    area_total = 0.0
    with obj_path.open('r', encoding='utf-8', errors='replace') as src:
        for line in src:
            if line.startswith('v '):
                t = line.split()
                if len(t) < 4:
                    raise ValueError('Malformed OBJ vertex line')
                v = tuple(float(x) for x in t[1:4])
                if not all(math.isfinite(x) for x in v):
                    raise ValueError('OBJ contains NaN/Infinity')
                vertices.append(v)
            elif line.startswith('f '):
                f = []
                for token in line.split()[1:]:
                    num = token.split('/')[0]
                    if not num:
                        raise ValueError('Malformed OBJ face index')
                    idx = int(num)
                    i = idx - 1 if idx > 0 else len(vertices) + idx
                    if i < 0 or i >= len(vertices):
                        raise ValueError('OBJ face index out of range')
                    f.append(i)
                if len(f) < 3:
                    continue
                for j in range(1, len(f)-1):
                    p0,p1,p2=(vertices[f[k]] for k in (0,j,j+1))
                    ab = [p1[i]-p0[i] for i in range(3)]
                    ac = [p2[i]-p0[i] for i in range(3)]
                    cr = (ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
                    area = 0.5 * math.sqrt(sum(c*c for c in cr))
                    if area <= 1e-12:
                        continue
                    area_total += area
                    triangles.append((p0,p1,p2))
                    cumulative.append(area_total)
    if not triangles:
        raise ValueError('OBJ contains no non-degenerate triangles')
    n = max(1000, min(max_points, math.ceil(area_total/(spacing*spacing))))
    ply_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    with ply_path.open('wb') as f:
        header = ('ply\nformat binary_little_endian 1.0\n'
                 'element vertex %d\n'
                 'property float x\nproperty float y\nproperty float z\n'
                 'end_header\n') % n
        f.write(header.encode('ascii'))
        for _ in range(n):
            tri = triangles[min(bisect.bisect_left(cumulative, rng.random() * area_total), len(triangles)-1)]
            u,v=rng.random(),rng.random()
            su=math.sqrt(u)
            a,b,c=1-su,su*(1-v),su*v
            point=tuple(a*tri[0][k]+b*tri[1][k]+c*tri[2][k] for k in range(3))
            f.write(struct.pack('<fff',*point))
    return n, len(triangles), area_total



def write_stl(obj, depsgraph, dst, unit):
    evaluated, mesh = actual_mesh(obj, depsgraph)
    try:
        tris = mesh.loop_triangles
        with dst.open('wb') as f:
            f.write(b'Air-FAR collision STL'.ljust(80, b'\0'))
            f.write(struct.pack('<I', len(tris)))
            for t in tris:
                points = [transform_xyz(obj.matrix_world, mesh.vertices[i].co, unit) for i in t.vertices]
                if obj.matrix_world.determinant() < 0:
                    points.reverse()
                # Blender tessellation is triangulated; Gazebo can calculate normals if zero.
                f.write(struct.pack('<3f', 0.0, 0.0, 0.0))
                for v in points:
                    f.write(struct.pack('<3f', *v))
                f.write(struct.pack('<H', 0))
        return len(tris)
    finally:
        evaluated.to_mesh_clear()


def box_from_object(obj, unit):
    bounds = [mathutils.Vector(c) for c in obj.bound_box]
    lows = [min(float(p[i]) for p in bounds) for i in range(3)]
    highs = [max(float(p[i]) for p in bounds) for i in range(3)]
    center = mathutils.Vector([(lows[i] + highs[i]) / 2 for i in range(3)])
    sizes_local = [highs[i] - lows[i] for i in range(3)]
    if any(z < 1e-4 for z in sizes_local):
        raise ValueError("COL_BOX object has a zero-thickness side: " + obj.name)
    scale = obj.matrix_world.to_scale()
    sizes = [abs(sizes_local[i] * scale[i] * unit) for i in range(3)]
    origin = transform_xyz(obj.matrix_world, center, unit)
    rot = obj.matrix_world.to_euler('XYZ')
    return origin, rot, sizes


def make_sdf(name, visual_parts, colliders, out_file):
    sdf = ET.Element('sdf', version='1.6')
    model = sub(sdf, 'model', name=name)
    sub(model, 'pose', '0 0 0 0 0 0')
    sub(model, 'static', 'true')
    link = sub(model, 'link', name='world_geometry')
    for filename, material_name, rgb in visual_parts:
        visual = sub(link, 'visual', name='visual_' + material_name)
        vgeo = sub(visual, 'geometry')
        vmesh = sub(vgeo, 'mesh')
        sub(vmesh, 'uri', 'model://%s/meshes/%s' % (name, filename))
        mat = sub(visual, 'material')
        rgba = ' '.join(nfmt(v) for v in (*rgb, 1.0))
        sub(mat, 'ambient', rgba)
        sub(mat, 'diffuse', rgba)
        # Low emission improves legibility in enclosed corridor simulations.
        # Gazebo will still use the original diffuse color.
        sub(mat, 'emissive', ' '.join(nfmt(v) for v in (*[0.06*c for c in rgb], 1.0)))
    for idx, c in enumerate(colliders):
        el = sub(link, 'collision', name='collision_%04d' % idx)
        if c['type'] == 'box':
            xyz, rpy, sizes = c['position'], c['rpy'], c['size']
            sub(el, 'pose', ' '.join(nfmt(v) for v in [*xyz, *rpy]))
            geom = sub(el, 'geometry')
            b = sub(geom, 'box')
            sub(b, 'size', ' '.join(nfmt(x) for x in sizes))
        else:
            geo = sub(el, 'geometry')
            mes = sub(geo, 'mesh')
            sub(mes, 'uri', 'model://%s/meshes/%s' % (name, c['filename']))
    xml_to_file(sdf, out_file)


def make_world(name, out_file):
    sdf = ET.Element('sdf', version='1.6')
    w = sub(sdf, 'world', name='default')
    scene = sub(w, 'scene')
    sub(scene, 'ambient', '0.55 0.55 0.55 1')
    sub(scene, 'background', '0.68 0.72 0.78 1')
    for model in ('sun', name):
        inc = sub(w, 'include')
        sub(inc, 'uri', 'model://' + model)
    sub(w, 'plugin', name='ros_interface_plugin', filename='librotors_gazebo_ros_interface_plugin.so')
    spherical = sub(w, 'spherical_coordinates')
    sub(spherical, 'surface_model', 'EARTH_WGS84')
    sub(spherical, 'latitude_deg', '47.3667')
    sub(spherical, 'longitude_deg', '8.5500')
    sub(spherical, 'elevation', '500.0')
    sub(spherical, 'heading_deg', '0')
    physics = sub(w, 'physics', type='ode')
    ode = sub(physics, 'ode')
    solver = sub(ode, 'solver')
    sub(solver, 'type', 'quick')
    sub(solver, 'iters', '1000')
    sub(solver, 'sor', '1.3')
    constraints = sub(ode, 'constraints')
    for key, value in [('cfm','0'),('erp','0.2'),('contact_max_correcting_vel','100'),('contact_surface_layer','0.001')]:
        sub(constraints,key,value)
    for key,value in [('max_step_size','0.001'),('real_time_factor','1'),('real_time_update_rate','1000'),('gravity','0 0 -9.8')]:
        sub(physics,key,value)
    xml_to_file(sdf,out_file)


def make_model_config(name, out_file):
    model = ET.Element('model')
    sub(model,'name',name)
    sub(model,'version','1.0')
    sub(model,'sdf','model.sdf',version='1.6')
    sub(model,'description','Blender static UAV navigation environment for Air-FAR')
    xml_to_file(model,out_file)


def make_launch(name, spawn, out_file):
    launch = ET.Element('launch')
    sub(launch,'arg',name='gazebo_gui',default='false')
    sub(launch,'arg',name='config',default='indoor')
    include = sub(launch,'include',file='$(find vehicle_simulator)/launch/system_gazebo.launch')
    for k, v in [('map_name',name),('gazebo_gui','$(arg gazebo_gui)'),('config','$(arg config)'),
                 ('vehicleX',nfmt(spawn[0])),('vehicleY',nfmt(spawn[1])),
                 ('vehicleZ',nfmt(spawn[2])),('vehicleYaw',nfmt(spawn[3]))]:
        sub(include,'arg',name=k,value=v)
    xml_to_file(launch,out_file)


def export_bundle(context, output_folder, name, use_zip):
    scene = context.scene
    scene_objs = list(scene.objects)
    visual_objs = [o for o in scene_objs if o.type == 'MESH' and not o.name.upper().startswith(('COL_', 'COLBOX_', 'NOEXPORT_'))]
    if not visual_objs:
        raise ValueError('No visual meshes. Add a Mesh object not named COL_ or NOEXPORT_.')
    coll_objs = [o for o in scene_objs if o.type == 'MESH' and o.name.upper().startswith(('COL_', 'COLBOX_'))]
    warnings = []
    if not coll_objs:
        coll_objs = visual_objs
        warnings.append('No COL_ meshes found; using ALL visual geometry for collision. For large scenes, create simplified COL_ collision meshes.')
    marker = next((o for o in scene_objs if o.name.upper() in ('UAV_SPAWN','SPAWN_UAV')),None)
    unit = float(scene.unit_settings.scale_length) or 1.0
    if marker:
        p = marker.matrix_world.translation
        spawn = [p.x*unit, p.y*unit, p.z*unit, marker.matrix_world.to_euler('XYZ').z]
    else:
        spawn = [0.0,0.0,1.5,0.0]
        warnings.append('UAV_SPAWN marker not found. Using default (0, 0, 1.5) meters and yaw=0 rad.')
    if any(not math.isfinite(float(a)) for a in spawn):
        raise ValueError('Invalid UAV_SPAWN position')
    out_root = Path(output_folder).expanduser().resolve()
    pkg = out_root / (name+'_gazebo_bundle')
    # This is a fully generated bundle directory. Clear stale OBJ/collision
    # files from prior exports to avoid importing old meshes after overwrite.
    if pkg.is_dir():
        shutil.rmtree(pkg)
    model_dir = pkg / 'model' / name
    mesh_dir = model_dir / 'meshes'
    tex_dir = model_dir / 'materials' / 'textures'
    preview_dir = model_dir / 'preview'
    world_dir = pkg / 'world'
    launch_dir = pkg / 'launch'
    for d in (mesh_dir, tex_dir, preview_dir, world_dir, launch_dir):
        d.mkdir(parents=True, exist_ok=True)
    depsgraph = context.evaluated_depsgraph_get()
    vtris = write_obj(visual_objs, depsgraph, mesh_dir, tex_dir, unit, warnings)
    visual_parts = split_visuals_by_material(mesh_dir, warnings)
    preview_count, preview_triangles, preview_area = sample_obj_to_ply(
        mesh_dir / 'visual.obj', preview_dir / 'pointcloud.ply', spacing=0.16, max_points=250000)
    collisions = []
    total_ctris = 0
    for index, o in enumerate(coll_objs):
        if o.name.upper().startswith(('COL_BOX_', 'COLBOX_')):
            origin, rotation, size = box_from_object(o, unit)
            collisions.append(dict(type='box',position=origin,rpy=tuple(rotation),size=size))
        else:
            filename = 'collision_%04d.stl' % index
            n = write_stl(o, depsgraph,mesh_dir/filename,unit)
            if n > 0:
                collisions.append(dict(type='mesh',filename=filename))
                total_ctris += n
    if not collisions:
        raise ValueError('Collision mesh is empty; please create 3D collider objects')
    if total_ctris > 100000:
        warnings.append('Complex collision geometry: %d triangles. Reduce COL_ geometry for Gazebo performance.' % total_ctris)
    make_sdf(name, visual_parts, collisions, model_dir/'model.sdf')
    make_world(name, world_dir/(name+'.world'))
    make_model_config(name, model_dir/'model.config')
    make_launch(name, spawn, launch_dir/('start_'+name+'.launch'))
    manifest = dict(map_name=name,spawn=dict(x=spawn[0],y=spawn[1],z=spawn[2],yaw_radians=spawn[3]),
                    geometry=dict(visual_triangles=vtris,visual_materials=len(visual_parts),collision_mesh_triangles=total_ctris,collision_objects=len(collisions),overview_points=preview_count),
                    warnings=warnings,system='ROS Noetic + Gazebo Classic 11 + Air-FAR')
    (pkg/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    installer_src = Path(__file__).resolve().parent / 'install_map.py'
    if installer_src.exists():
        shutil.copy2(installer_src, pkg/'install_map.py')
    else:
        warnings.append('INSTALLER NOT FOUND: install_map.py beside the add-on is required for automatic installation')
    instructions = ("Air-FAR Gazebo Classic map export: %s\n\n" % name +
        "1. Copy this entire *_gazebo_bundle folder or its zip to your Ubuntu VM.\n"+
        "2. Ubuntu: python3 install_map.py --workspace ~/airfar_ws/aerial_autonomy_development_environment\n"+
        "3. Simulator: source /opt/ros/noetic/setup.bash; source ~/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash\n"+
        "   roslaunch vehicle_simulator start_%s.launch\n" % name +
        "4. Planner (new terminal): source /opt/ros/noetic/setup.bash; source ~/airfar_ws/aerial_autonomy_development_environment/devel/setup.bash; source ~/airfar_ws/Air-FAR/devel/setup.bash\n"+
        "   roslaunch airfar_planner airfar.launch config_file:=default rviz_file:=airfar_tunnel\n"+
        "5. Check: rosnode ping -c 1 /gazebo; rostopic hz /registered_scan; rostopic echo -n 1 /state_estimation/pose/pose/position\n\n"+
        "Spawn from Blender UAV_SPAWN object (meters, yaw in radians): %s\n" % repr(spawn)+
        "Note: Visuals are split by material with explicit SDF ambient/diffuse colors.\n"+
        "Full static overview preview/pointcloud.ply is generated for RViz visualization only (not navigation prior).\n"+
        "Do not assume all Blender effects / Geometry Nodes / PBR materials are exported.\n"+
        "Notes:\n- "+'\n- '.join(warnings)+"\n")
    (pkg/'README.txt').write_text(instructions,encoding='utf-8')
    if use_zip:
        zpath=out_root / (name+'_gazebo_bundle.zip')
        with zipfile.ZipFile(zpath, 'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for f in pkg.rglob('*'):
                if f.is_file():
                    z.write(f,arcname=f.relative_to(pkg))
    return pkg, vtris, total_ctris, warnings


class AIRFAR_OT_export_gazebo(bpy.types.Operator):
    bl_idname='airfar.export_gazebo'
    bl_label='One-click Export for Gazebo'
    bl_description='Create a Gazebo Classic map, COLLISION, world, and UAV_SPAWN bundle'
    bl_options={'REGISTER'}

    def execute(self,context):
        s=context.scene
        try:
            name=s.airfar_map_name.strip() or Path(bpy.data.filepath).stem or 'my_maze'
            name=safe_name(name)
            out=bpy.path.abspath(s.airfar_export_folder)
            pkg, vt,ct,warn=export_bundle(context,out,name, s.airfar_zip)
            self.report({'INFO'}, 'Gazebo bundle exported: %s | visual=%d collision=%d' % (pkg,vt,ct))
            for msg in warn[:5]:
                print('[Air-FAR EXPORT WARNING]',msg)
            print('[Air-FAR EXPORT]',pkg,'warnings=',warn)
            return {'FINISHED'}
        except Exception as ex:
            traceback.print_exc()
            self.report({'ERROR'},str(ex)[:220])
            return {'CANCELLED'}


class AIRFAR_PT_gazebo_panel(bpy.types.Panel):
    bl_label='Air-FAR Gazebo Map'
    bl_idname='AIRFAR_PT_gazebo_panel'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Gazebo'

    def draw(self,context):
        l=self.layout
        s=context.scene
        l.prop(s,'airfar_map_name',text='Map name')
        l.prop(s,'airfar_export_folder',text='Output folder')
        l.prop(s,'airfar_zip',text='Create ZIP')
        l.label(text='Spawn: add Empty named UAV_SPAWN')
        l.label(text='Boxes: name COL_BOX_...')
        l.label(text='Meshes: name COL_...')
        l.label(text='v0.3: Principled BSDF Base Color to SDF')
        l.operator('airfar.export_gazebo',icon='EXPORT')


classes=(AIRFAR_OT_export_gazebo,AIRFAR_PT_gazebo_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.airfar_map_name=StringProperty(name='Map name',default='my_maze')
    bpy.types.Scene.airfar_export_folder=StringProperty(name='Output folder',subtype='DIR_PATH',default='//gazebo_exports')
    bpy.types.Scene.airfar_zip=BoolProperty(name='Create ZIP',default=True)


def unregister():
    del bpy.types.Scene.airfar_map_name
    del bpy.types.Scene.airfar_export_folder
    del bpy.types.Scene.airfar_zip
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__=='__main__':
    register()
