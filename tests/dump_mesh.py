import struct, numpy as np
with open('examples/example.stl','rb') as f:
    f.read(80)
    n=struct.unpack('<I',f.read(4))[0]
    verts=[]
    for i in range(n):
        f.read(12)
        for j in range(3):
            x,y,z=struct.unpack('<fff',f.read(12))
            verts.append([x,y,z])
        f.read(2)
v=np.array(verts)
unique_v = np.unique(v, axis=0)
print(f'{n} triangles, {len(unique_v)} unique vertices')
print('Unique vertices (STL / Uranium Y-up coords):')
for vv in unique_v:
    print(f'  X={vv[0]:8.2f}  Y={vv[1]:8.2f}  Z={vv[2]:8.2f}')

# Convert to gcode Z-up
gv = np.column_stack([unique_v[:,0], -unique_v[:,2], unique_v[:,1]])
print('\nAfter Z-up conversion (before bed offset):')
for vv in gv:
    print(f'  X={vv[0]:8.2f}  Y={vv[1]:8.2f}  Z={vv[2]:8.2f}')

# The gcode says MINX:43 MAXX:153.249 MINY:82 MAXY:118 MINZ:0.3 MAXZ:3.9
# So gcode X range = 110.249, Y range = 36
# But mesh X range = 100, mesh Y (after conv) = 4
# Y is wrong - the mesh is very thin in Y
print(f'\nMesh X span: {gv[:,0].max()-gv[:,0].min():.1f}')
print(f'Mesh Y span: {gv[:,1].max()-gv[:,1].min():.1f}')
print(f'Mesh Z span: {gv[:,2].max()-gv[:,2].min():.1f}')
print(f'GCode X span: {153.249-43:.1f}')
print(f'GCode Y span: {118-82:.1f}')
print(f'GCode Z span: {3.9-0.3:.1f}')
