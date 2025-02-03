from utils import execute_ssh_command, get_logger, write_minions, get_minions

logger = get_logger()

def image_minion(minion_ip, system_name="lilo"):
    """Start imaging process on a minion with additional parameters.

    Args:
        minion_ip (str): The IP address of the minion.
        system_name (str, optional): The name of the system. Defaults to "lilo".

    Returns:
        bool: True if the imaging process was successfully initiated, False otherwise.
    """
    
    # Get minion configuration
    minion_config = get_minions(minion_ip)
    if not minion_config:
        logger.error(f"No configuration found for minion {minion_ip}")
        return False
    
    # Extract camera coordinates and say that positioning needed in case not present
    try:
        coordinates_cam1 = minion_config['cameras']['camera1']['camera_pos']
        coordinates_cam2 = minion_config['cameras']['camera2']['camera_pos']
    except KeyError:
        logger.error(f"Missing camera coordinates for minion {minion_ip}. Run positioning module first.")
        write_minions(minion_ip, "position needed", updated=True)
        return False

    logger.debug(f"Initiating imaging on minion {minion_ip}")
    write_minions(minion_ip, "imaging")

    # Execute imaging on minion
    command = f"python3 minion.py --system {system_name} --module {minion_ip} --coordinates_cam1 '{coordinates_cam1}' --coordinates_cam2 '{coordinates_cam2}'"
    result = execute_ssh_command('minion', command, ip=minion_ip, timeout=300)
    
    # Pure logging results:
    if not result['success']:
        logger.error(f"Imaging failed on minion {minion_ip}: {result['error']}")
        write_minions(minion_ip, "error", updated=True)
        return False
    
    # Parse output to get detailed status
    output_lines = result['output'].strip().split('\n')
    
    if "Partial success" in result['output']:
        
        failed_cameras = []
        
        for line in output_lines:
            
            # Find a failed camera from output
            if "Failed cameras:" in line:
                failed_info = line.split("Failed cameras:")[1].strip()
                failed_cameras = [cam.strip() for cam in failed_info.split(';')]
        
        logger.warning(f"Partial imaging success on minion {minion_ip}. Failed: {', '.join(failed_cameras)}")
        write_minions(minion_ip, f"partial - {', '.join(failed_cameras)}", updated=True) # Update camera status
        
        return False
    
    elif "Error: No images" in result['output']:
        logger.error(f"No images captured on minion {minion_ip}")
        write_minions(minion_ip, "error", updated=True)
        
        return False
    
    logger.info(f"Imaging completed successfully on minion {minion_ip}")
    write_minions(minion_ip, "ready", updated=True)
    
    return True
    
def image_all_minions(system_name="lilo"):
    """Image all minions listed in the minions.yaml file and update their status.
    
    Args:
        system_name (str): The name of the system to be imaged (default is "lilo").
    
    Returns:
        dict: A dictionary containing the imaging results for each minion. The keys are the minion IPs and the values are
        boolean values indicating whether the imaging was successful or not.
    """
    
    # Load minions configuration
    minions_config = get_minions()
    results = {}
    
    for minion_ip in minions_config:
        logger.info(f"Imaging minion: {minion_ip}")
        results[minion_ip] = image_minion(minion_ip, system_name)
        logger.info(f"Imaging completed for {minion_ip} - Success: {results[minion_ip]}")

    return results

image_all_minions()
