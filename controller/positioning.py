from utils import get_logger, write_minions, execute_ssh_command, get_minions, receive_file
import time

logger = get_logger()

# TODO Implement timeout
def monitor_position(x, y):
    """Monitor for one position request and assign given coordinates."""
    while True:
        try:
            minions = get_minions()
            unpositioned = set(minions.keys()) # TODO capture positioned minions
            request_found = False

            for minion_ip in unpositioned:
                result = receive_file('minion', 'requestLocation.file', 'config/requestLocation.file', ip=minion_ip)
                    
                if result['success']:
                    logger.info(f"Position request from {minion_ip}")
                    
                    if write_minions(minion_ip, "online", cam1_position=f"X{x}Y{y}", cam2_position=f"X{x}Y{int(y)+1}"):
                        
                        # Clear request files from all unpositioned minions
                        for ip in unpositioned:
                            execute_ssh_command('minion', 'rm -f requestLocation.file', ip=ip)
                            
                        return True
            
            if not request_found:
                time.sleep(2)
            
        except Exception as e:
            logger.error(f"Monitor error: {str(e)}")
            time.sleep(5)
    
monitor_position(1,1)