import re

with open('examples/example_enabled_zaa.gcode') as f:
    lines = f.readlines()

with open('examples/example_disabled_zaa.gcode') as f:
    disabled = f.read()

prev_e = None
errors = 0
for i, line in enumerate(lines):
    # Skip G92 resets
    if 'G92' in line:
        prev_e = None
        continue
    m = re.search(r'E([-\d.]+)', line)
    if m and 'G1' in line:
        e = float(m.group(1))
        # Retraction (F1500) is allowed to drop E
        if prev_e is not None and e < prev_e - 0.01 and 'F1500 E' not in line:
            errors += 1
            if errors <= 10:
                print(f'Line {i+1}: E DROPPED {prev_e:.5f} -> {e:.5f}')
                print(f'  {line.strip()}')
                print(f'  prev: {lines[i-1].strip()}')
        prev_e = e

print(f'\nTotal E discontinuities (excluding retractions): {errors}')

# Compare total extrusion
en_total = 0
dis_total = 0
for line in lines:
    m = re.search(r'G1.*E([\d.]+)', line)
    if m:
        en_total = float(m.group(1))
for line in disabled.split('\n'):
    m = re.search(r'G1.*E([\d.]+)', line)
    if m:
        dis_total = float(m.group(1))

print(f'\nFinal E - disabled: {dis_total:.3f}')
print(f'Final E - enabled:  {en_total:.3f}')
print(f'Difference: {en_total - dis_total:.3f} ({(en_total/dis_total - 1)*100:.1f}%)')

# Count ZAA markers
zaa_count = sum(1 for l in lines if 'ZAA_RESET' in l)
print(f'\nZAA_RESET count: {zaa_count}')
