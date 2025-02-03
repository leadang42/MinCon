import logging
import os
from datetime import datetime
import yaml
import subprocess

MINIONS_YAML = "config/minions.yaml"

# LOGGER #
_logger = None

# LOGGER #
def get_logger(reset=False, log_file=None, level=logging.INFO):
    """
    Get or create the global logger instance.

    Parameters:
        reset (bool): Whether to reset the logger configuration.
        log_file (str): The name of the log file. If None, a timestamped log file will be generated.
        level (int): The logging level to set for the logger.

    Returns:
        logging.Logger: The global logger instance.
    """
    global _logger
    
    # Return existing logger if already configured and reset not requested
    if _logger is not None and not reset:
        return _logger
        
    # Create new logger or reset existing one
    _logger = logging.getLogger('minion_system')
    
    # Reset handlers if requested or if logger doesn't exist
    if reset or not _logger.handlers:
        _logger.handlers.clear()
        _logger.setLevel(level)
        
        # Generate timestamped log file if none provided
        if log_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = f'minion_system_{timestamp}.log'
            
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        log_path = os.path.join('logs', log_file)
        
        # File handler
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(module)s - %(funcName)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        _logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            '%(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        _logger.addHandler(console_handler)
        
    return _logger

# YAML FUNCTIONS #
def load_yaml(file_path):
    """
    Loads a YAML file and returns the parsed data.

    Args:
        file_path (str): The path to the YAML file.

    Returns:
        dict: The parsed data from the YAML file.

    Raises:
        FileNotFoundError: If the specified file_path does not exist.
        yaml.YAMLError: If there is an error parsing the YAML file.

    """
    try:
        with open(file_path, 'r') as file:
            return yaml.safe_load(file)
        
    except FileNotFoundError:
        return None
        
    except yaml.YAMLError:
        return None

def write_yaml(data, file_path):
    """
    Writes data to a YAML file.

    Args:
        data: The data to be written to the YAML file.
        file_path: The path of the YAML file.

    Returns:
        True if the data is successfully written to the file.
        False if there is an error while writing the data to the file.
    """
    try:
        with open(file_path, 'w') as file:
            yaml.safe_dump(data, file, default_flow_style=False)
        return True
        
    except (IOError, yaml.YAMLError):
        return False

def write_minions(minion_ip, status, cam1_status=None, cam2_status=None, updated=False, cam1_position=None, cam2_position=None):
    """Update the status of a specific minion and its cameras in the YAML file.

    Args:
        minion_ip (str): The IP address of the minion.
        status (str): The status to update for the minion.
        cam1_status (str, optional): Status for camera1.
        cam2_status (str, optional): Status for camera2.
        updated (bool, optional): Whether to update the last_update field.

    Returns:
        bool: True if the YAML file was successfully updated.
    """
    data = load_yaml(MINIONS_YAML) or {}
    
    if minion_ip not in data:
        data[minion_ip] = {"cameras": {"camera1": {}, "camera2": {}}}
    
    data[minion_ip].update({
        "status": status,
        "last_accessed": datetime.now().isoformat(),
        "last_update": datetime.now().date().isoformat() if updated else data[minion_ip].get("last_update")
    })
    
    current_time = datetime.now().isoformat()
    if cam1_status:
        data[minion_ip]["cameras"]["camera1"].update({
            "status": cam1_status,
            "last_captured": current_time
        })
    
    if cam2_status:
        data[minion_ip]["cameras"]["camera2"].update({
            "status": cam2_status,
            "last_captured": current_time
        })
    
    if cam1_position: data[minion_ip]["cameras"]["camera1"]["camera_pos"] = cam1_position
    if cam2_position: data[minion_ip]["cameras"]["camera2"]["camera_pos"] = cam2_position
    
    return write_yaml(data, MINIONS_YAML)

def get_minions(minion_ip=None):
    """
    Retrieve the minion information based on the provided minion IP address(es).

    Args:
        minion_ip (str, list, None): The IP address(es) of the minion(s).
            Can be a single IP string, list of IP strings, or None to return all minions.

    Returns:
        dict: Dictionary containing the requested minion information.
            - If minion_ip is None: Returns all minion data
            - If minion_ip is a string: Returns dict data of single IP
            - If minion_ip is a list: Returns dict with matching IPs as keys 
    """
    data = load_yaml(MINIONS_YAML) or {}
    
    # Return all data if no IP specified
    if minion_ip is None:
        return data
        
    # Handle single IP case
    if isinstance(minion_ip, str):
        return data[minion_ip] if minion_ip in data else {}
        
    # Handle list of IPs case
    if isinstance(minion_ip, list):
        return {ip: data[ip] for ip in minion_ip if ip in data}
        
    # Return empty dict for invalid input type
    return {}
    
# SSH FUNCTIONS #
def _run_ssh_command(command, timeout=None):
    """Internal helper to run a shell command and return result."""
    logger = get_logger()
        
    try:
        # Only log non-trivial commands at debug level
        if not command.startswith(('cat', 'echo', 'rm')):
            logger.debug(f"Executing command: {command}")
            
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        
        if result.returncode != 0:
            
            # TODO Separate this logic from this ssh operation somehow 
            # This logic is here so that no error is printed for wrong ssh request
            if "requestLocation.file" not in command: 
                logger.error(f"Command ({command}) failed with error: {result.stderr}")
            else:
                print("Press minion button")
            
        return {
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr if result.returncode != 0 else None
        }
        
    except Exception as e:
        logger.error(f"Exception during command ({command}) execution: {str(e)}")
        return {'success': False, 'output': '', 'error': str(e)}

def _get_target_ip(config, connection_type, ip=None):
    """Internal helper to get target IP based on connection type."""
    logger = get_logger()
        
    if not config:
        logger.error("Could not load config file")
        raise ValueError("Could not load config file")
    
    if connection_type not in ['minion', 'router']:
        logger.error(f"Invalid connection type: {connection_type}")
        raise ValueError("connection_type must be either 'minion' or 'router'")
            
    params = config[connection_type]
    
    if connection_type == 'router':
        if 'host' not in params:
            logger.error("Host not specified in router config")
            raise ValueError("Host not specified in router config")
        return params['host'], params
    
    if not ip:
        logger.error("IP required for minion connection")
        raise ValueError("IP required for minion")
    
    logger.debug(f"Target IP resolved: {ip if connection_type == 'minion' else params['host']}")
    return ip, params

def execute_ssh_command(connection_type, command, ip=None, sudo=False, timeout=None):
    """
    Execute SSH command on remote host.

    Args:
        connection_type (str): The type of connection to use (e.g., 'ssh', 'telnet').
        command (str): The command to execute on the remote host.
        ip (str, optional): The IP address of the remote host. Defaults to None.
        sudo (bool, optional): Whether to execute the command with sudo privileges. Defaults to False.
        timeout (float, optional): The maximum time to wait for the command to complete. Defaults to None.

    Returns:
        str: The output of the executed command.

    """
    target_ip, params = _get_target_ip(load_yaml('config/config.yaml'), connection_type, ip)

    if sudo:
        ssh_command = f'sshpass -p "{params["password"]}" ssh {params["options"]} {params["user"]}@{target_ip} "echo \'{params["password"]}\' | sudo -S {command}"'
    else:
        ssh_command = f'sshpass -p "{params["password"]}" ssh {params["options"]} {params["user"]}@{target_ip} "{command}"' 
        
    return _run_ssh_command(ssh_command, timeout)

def transfer_file(connection_type, source, dest, ip=None):
    """Transfer file to remote host.

    Args:
        connection_type (str): The type of connection to the remote host.
        source (str): The path of the file to be transferred.
        dest (str): The destination path on the remote host.
        ip (str, optional): The IP address of the remote host. Defaults to None.

    Returns:
        str: The output of the SSH command used for file transfer.
    """
    target_ip, params = _get_target_ip(load_yaml('config/config.yaml'), connection_type, ip)
    scp_command = f'sshpass -p "{params["password"]}" scp {params["options"]} {source} {params["user"]}@{target_ip}:{dest}'
    
    return _run_ssh_command(scp_command)

def receive_file(connection_type, remote_path, local_path, ip=None):
    """
    Retrieve file from remote host.

    Args:
        connection_type (str): The type of connection to establish with the remote host.
        remote_path (str): The path of the file on the remote host.
        local_path (str): The path where the file will be saved locally.
        ip (str, optional): The IP address of the remote host. Defaults to None.

    Returns:
        str: The output of the SSH command executed to retrieve the file.

    """
    target_ip, params = _get_target_ip(load_yaml('config/config.yaml'), connection_type, ip)
    scp_command = f'sshpass -p "{params["password"]}" scp {params["options"]} {params["user"]}@{target_ip}:{remote_path} {local_path}'

    return _run_ssh_command(scp_command)