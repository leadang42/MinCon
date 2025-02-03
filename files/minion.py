import argparse
import csv
from datetime import datetime
import time
from pathlib import Path
from picamera2 import Picamera2
import time

def ensure_directory_structure():
    current_date = datetime.now().strftime("%d%m%Y")
    image_dir = Path.home() / 'Documents' / 'images' / current_date
    image_dir.mkdir(parents=True, exist_ok=True)
    return image_dir

def write_status_log(log_file, captures, base_path=Path.home() / 'Documents'):
    row_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'SUCCESS' if all(c['success'] for c in captures.values()) else 
                 'PARTIAL' if any(c['success'] for c in captures.values()) else 'FAILED'
    }
    
    # Create one line for the csv file
    for cam_id, capture in captures.items():
        
        row_data[f'cam{cam_id}_path'] = capture['path'] if capture['success'] else ''
        
        if not capture['success'] and capture['error']:
            row_data[f'cam{cam_id}_error'] = capture['error']
    
    try:
        # Write csv without pandas so that pandas doesn't need to be installed
        log_path = base_path / log_file
        
        headers = ['timestamp', 'status'] + [f'cam{i}_{field}' for i in captures.keys() for field in ['path', 'error']]
        file_exists = log_path.exists()
        
        with open(log_path, mode='a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            
            if not file_exists:
                writer.writeheader()
                
            writer.writerow(row_data)
            
        return True
    
    except Exception as e:
        print(f"Log write failed: {e}")
        return False

def take_images(log_file, system, module, coordinates_cam1, coordinates_cam2):
    captures = {
        1: {'success': False, 'path': None, 'error': None},
        2: {'success': False, 'path': None, 'error': None}
    }
    
    for cam_id, coords in [(1, coordinates_cam1), (2, coordinates_cam2)]:
        try:
            # Start configuration of individual camera
            camera = Picamera2(camera_num=cam_id-1)
            camera.configure(camera.create_still_configuration())
            camera.start()
            time.sleep(0.5)
            
            # Create filename from args in main
            filename = f"{system}_{module}_cam{cam_id}_{int(time.time())}_{coords}.png"
            
            # Create directory where images are stored
            image_dir = ensure_directory_structure()
            
            # Start imaging of individual camera
            camera.capture_file(str(image_dir / filename))
            
            # No exception was raised during init and imaging
            captures[cam_id].update({
                'success': True,
                'path': f"documents/images/{datetime.now():%Y%m%d}/{filename}"
            })
    
        except Exception as e:
            captures[cam_id]['error'] = str(e)
    
    write_status_log(log_file, captures)
    
    # Only returns True when both cameras successfull
    return any(c['success'] for c in captures.values()), captures

def main():
    parser = argparse.ArgumentParser(description='Capture images from dual cameras')
    parser.add_argument('--system', required=True, help='System machine identifier')
    parser.add_argument('--module', required=True, help='Minion identifier')
    parser.add_argument('--coordinates_cam1', required=True, help='Position coordinates camera 1')
    parser.add_argument('--coordinates_cam2', required=True, help='Position coordinates camera 2')
    
    args = parser.parse_args()
    
    # Trigger imaging both cameras with arguments
    success, captures = take_images(
        'ImagingLog.csv',
        args.system,
        args.module,
        args.coordinates_cam1,
        args.coordinates_cam2
    )
    
    # Outputs for successfull and unsuccessfull imaging (always return 0, failures are handled my imaging module)
    if any(c['success'] for c in captures.values()):
        
        successful_cams = [f"Camera {i}" for i, c in captures.items() if c['success']]
        failed_cams = [f"Camera {i} ({c['error']})" for i, c in captures.items() if not c['success']]
        
        print(f"Partial success: Images captured from {' and '.join(successful_cams)}")
        
        if failed_cams:
            print(f"Failed cameras: {'; '.join(failed_cams)}")
            
        return 0
    
    print("Error: No images captured from either camera")
    return 0

if __name__ == "__main__":
    exit(main())