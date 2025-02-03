from datetime import datetime
import subprocess
import pandas as pd
from utils import get_minions, execute_ssh_command, transfer_file, receive_file, get_logger, write_minions

logger = get_logger()

# SEARCHING FOR MINIONS #
def read_current_leases(linux=True, select_hostname=None):
    """
    Discover all connected minions.

    Args:
        linux (bool, optional): Flag indicating if the system is running Linux. Defaults to True.
        select_hostname (str, optional): Hostname to filter the leases by. Defaults to None.

    Returns:
        pandas.DataFrame or None: DataFrame containing the discovered minions' leases information, or None if an error occurred.
    """
    logger.info("Starting minion discovery process")
    
    result = receive_file(
        "router",
        "/var/lib/misc/dnsmasq.leases", 
        'config/leases.csv'
    )
    
    if not result['success']:
        logger.error(f"Failed to retrieve lease file: {result['error']}")
        return None

    try:        
        leases = pd.read_csv(
            'config/leases.csv', 
            sep = ' ',
            names=['timestamp', 'mac', 'ip', 'hostname', 'client_id'] 
        )
        
        # Default always exclude host (Option just exists bc of Mac incompatibility with this ssh command)
        if linux:
            command = ['hostname', '-I'] 
            result = subprocess.run(command, capture_output=True, text=True)
            host_leases = result.stdout.strip().split()
            leases = leases[~leases.isin(host_leases).any(axis=1)]
            
        else:
            host_leases = []
            for interface in ['en0', 'en1']:
                result = subprocess.run(['ipconfig', 'getifaddr', interface], capture_output=True, text=True)
                if result.returncode == 0:
                    host_leases.append(result.stdout.strip())
            
            if host_leases:
                leases = leases[~leases['ip'].isin(host_leases)]
        
        if select_hostname: 
            leases = leases[leases['hostname'].str.contains(select_hostname, case=False)]
            
        leases.to_csv('config/leases.csv')
        logger.info(f"Successfully discovered {len(leases)} minions")
        
        return leases
        
    except Exception as e:
        logger.error(f"Error during minion discovery: {str(e)}")
        return None

# UPDATING MINIONS WITH FILES #
def has_run_today(minion_ip):
    """Check if minion was updated today using YAML tracking.

    Args:
        minion_ip (str): The IP address of the minion.

    Returns:
        bool: True if the minion was updated today, False otherwise.
    """
    minion = get_minions(minion_ip)
    
    last_update_date = minion.get("last_update", "")
    today = datetime.now().date().isoformat()
        
    if last_update_date == today:
        return True
    else:
        return False

def update_minion(minion_ip):
    """Update a single minion and track its status.

    This function performs a series of steps to update a minion with the given IP address.
    It configures power button settings, sets up system configuration files, applies core updates,
    configures system services, and tracks the status of the update process.

    Args:
        minion_ip (str): The IP address of the minion to be updated.

    Returns:
        bool: True if the update process is successful, False otherwise.
    """
    logger.info(f"Starting update process for minion: {minion_ip}")
    
    try:

        # System configuration files
        logger.info(f"[{minion_ip}] Setting up system configuration files...")
        if not all([
            transfer_file('minion', 'files/logind.conf', 'logind.conf', ip=minion_ip)['success'],
            execute_ssh_command('minion', 'mv logind.conf /etc/systemd/logind.conf', ip=minion_ip, sudo=True)['success'],
            transfer_file('minion', 'files/wayfire.ini', '.config/wayfire.ini', ip=minion_ip)['success'],
            transfer_file('minion', 'files/button.sh', 'button.sh', ip=minion_ip)['success'],
            execute_ssh_command('minion', 'chmod +x button.sh', ip=minion_ip, sudo=True)['success']
        ]):
            logger.error(f"[{minion_ip}] Failed to set up system configuration files")
            write_minions(minion_ip, "failed_config")
            return False

        # Core imaging module for minion
        logger.info(f"[{minion_ip}] Applying core updates...")
        if not all([
            transfer_file('minion', 'files/minion.py', 'minion.py', ip=minion_ip)['success'],
            execute_ssh_command('minion', 'raspi-config nonint do_wayland W2', ip=minion_ip, sudo=True)['success']
        ]):
            logger.error(f"[{minion_ip}] Failed to apply core updates")
            write_minions(minion_ip, "failed_core")
            return False
        
        # Configuring system services
        logger.info(f"[{minion_ip}] Configuring system services...")
        if not all([
            execute_ssh_command('minion', 'systemctl restart systemd-logind', ip=minion_ip, sudo=True)['success'],
            execute_ssh_command('minion', 'reboot', ip=minion_ip, sudo=True)['success']
        ]):
            logger.error(f"[{minion_ip}] Failed to configure system services")
            write_minions(minion_ip, "failed_services")
            return False

        # Update successful status
        write_minions(minion_ip, "online", updated=True)
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error updating minion {minion_ip}: {str(e)}")
        write_minions(minion_ip, f"error: {str(e)}")
        return False

def update_all_minions(linux=True, select_hostname=None, force_update=False):
    """
    Update all connected minions if they have not been updated today.

    Args:
        linux (bool, optional): Flag to indicate if the minions are running on Linux. Defaults to True.
        select_hostname (str, optional): Hostname of the specific minion to update. Defaults to None.

    Returns:
        None

    """
    logger.info("Starting fleet-wide minion update process")
    
    # Get IPs of all connected minions
    minions_df = read_current_leases(linux=linux, select_hostname=select_hostname)
    
    # Track stats for logging
    total, updated, skipped, failed = 0, 0, 0, 0
    
    # If there are minions connected
    if minions_df is not None and not minions_df.empty:
        total = len(minions_df['ip'])
        
        for ip in minions_df['ip']:
            if (not has_run_today(ip)) or force_update:
                
                if update_minion(ip):
                    updated += 1
                    logger.info(f"Successfully updated minion: {ip}")
                else:
                    failed += 1
                    logger.error(f"Failed to update minion: {ip}")
            else:
                skipped += 1
                logger.debug(f"Skipped {ip} - already updated today")
                
        logger.info(f"Update process completed. Total: {total}, Updated: {updated}, Skipped: {skipped}, Failed: {failed}")
    else:
        logger.warning("No minions found to update")

update_all_minions(False, "minionpi", force_update=False)
