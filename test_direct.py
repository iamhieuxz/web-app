import os
import sys

# Add project path
sys.path.insert(0, 'F:/web-app')

# Direct test of the stats logic
root = os.environ.get('GALLERY_DL_HOME', 'E:/gallery-dl')
norm_root = os.path.normpath(root)
print('Root:', norm_root)
print('Exists:', os.path.exists(norm_root))

if os.path.exists(norm_root):
    try:
        entries = os.listdir(norm_root)
        print('Entries:', len(entries))
        print('First few:', entries[:5])
    except Exception as e:
        print('Error listing:', e)
