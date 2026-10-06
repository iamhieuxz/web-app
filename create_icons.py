import base64
import struct
import zlib

def create_png(width, height, color):
    """Create a simple solid color PNG"""
    def png_chunk(chunk_type, data):
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', crc)
    
    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'
    
    # IHDR chunk
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    ihdr = png_chunk(b'IHDR', ihdr_data)
    
    # IDAT chunk - raw pixel data
    raw_data = b''
    r, g, b = color
    for y in range(height):
        raw_data += b'\x00'  # filter type
        for x in range(width):
            raw_data += bytes([r, g, b, 255])
    
    compressed = zlib.compress(raw_data)
    idat = png_chunk(b'IDAT', compressed)
    
    # IEND chunk
    iend = png_chunk(b'IEND', b'')
    
    return signature + ihdr + idat + iend

def create_icon_with_border(size):
    """Create icon with gradient-like effect using concentric rectangles"""
    # Sky blue color: #0ea5e9
    main_color = (14, 165, 233)
    dark_color = (3, 105, 161)
    
    raw_data = b''
    for y in range(size):
        raw_data += b'\x00'  # filter type
        for x in range(size):
            # Create a gradient effect based on distance from center
            dx = abs(x - size//2) / (size//2)
            dy = abs(y - size//2) / (size//2)
            dist = (dx*dx + dy*dy) ** 0.5
            
            if dist < 0.35:
                # Center - bright
                r, g, b = main_color
            elif dist < 0.45:
                # Border - dark
                r, g, b = dark_color
            else:
                # Outside - transparent (dark bg shows through)
                r, g, b = 0, 0, 0
            
            raw_data += bytes([r, g, b, 255])
    
    def png_chunk(chunk_type, data):
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', crc)
    
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    ihdr = png_chunk(b'IHDR', ihdr_data)
    compressed = zlib.compress(raw_data)
    idat = png_chunk(b'IDAT', compressed)
    iend = png_chunk(b'IEND', b'')
    
    return signature + ihdr + idat + iend

# Create icons folder
import os
os.makedirs('static/icons', exist_ok=True)

sizes = [72, 96, 128, 144, 152, 192, 384, 512]
for size in sizes:
    png_data = create_icon_with_border(size)
    with open(f'static/icons/icon-{size}.png', 'wb') as f:
        f.write(png_data)
    print(f'Created icon-{size}.png ({len(png_data)} bytes)')

print('Done!')
