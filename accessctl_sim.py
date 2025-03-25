from pymodbus.server import StartTcpServer, StartSerialServer
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.framer import FramerType
import threading
from blessed import Terminal
import yaml
from math import isclose
import time

PERIOD_S = 0.1

# Charger la configuration depuis le fichier YAML
with open('accessctl_sim.yaml', 'r') as file:
    config = yaml.safe_load(file)

# Configuration initiale
modbus_type = config['modbus']['type']
modbus_port = config['modbus']['port']
slave_address = config['modbus']['slave_address']
input_register_value = config['modbus']['input_register_value']
initial_angle = config['barrier']['initial_angle']
angular_speed = config['barrier']['angular_speed']

# Variables globales
barrier_angle = initial_angle
barrier_moving = 0
t = 0
# Création du contexte Modbus
store = ModbusSlaveContext(
    co=ModbusSequentialDataBlock(0, [0]*4),
    hr=ModbusSequentialDataBlock(0, [input_register_value])
)

# Fonction pour démarrer le serveur Modbus
def start_modbus_server():
    global store, wbarrier_angle, barrier_moving, input_register_value, t

    context = ModbusServerContext(slaves={slave_address:store}, single=False)

    # Identification du serveur
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'LPO Queneau'
    identity.ProductCode = 'LPOQ LNX Accessctl'
    identity.VendorUrl = 'https://bts-ciel-queneau.fr/'
    identity.ProductName = 'Accessctl pymodbus server'
    identity.ModelName = 'Accessctl pymodbus server'
    identity.MajorMinorRevision = '1.0'

    # Démarrage du serveur
    if modbus_type == 'rtu':
        StartSerialServer(context=context, framer=FramerType.RTU, identity=identity, port=modbus_port, timeout=1)
    elif modbus_type == 'tcp':
        StartTcpServer(context, identity=identity, address=("0.0.0.0", 502))


# Fonction pour mettre à jour la valeur de l'input register
def update_input_register_value(new_value):
    global input_register_value, store
    input_register_value = new_value
    store.setValues(3, 0, [new_value >> 8, new_value & 0xff])

# Fonction pour mettre à jour l'angle de la barrière
def update_barrier_angle():
    global barrier_angle, barrier_moving, t, store
    while True:
        # l'arrêt est prioritaire, puis l'ouverture
        ouvrir, fermer, arreter = store.getValues(5, 0, 3)
        if fermer and not isclose(barrier_angle, 0, abs_tol = 0.1):
            barrier_moving = -1
            store.setValues(5, 1, [0])
        if ouvrir and not isclose(barrier_angle, 90.0, abs_tol = 0.1):
            barrier_moving = 1
            store.setValues(5, 0, [0])
        if arreter:
            barrier_moving = 0
            store.setValues(5, 2, [0])
        if barrier_moving:
            barrier_angle += angular_speed * PERIOD_S * barrier_moving
            if isclose(barrier_angle, 0.0, abs_tol = 0.1) or isclose(barrier_angle, 90.0, abs_tol = 0.1):
                barrier_moving = 0
        t += PERIOD_S
        time.sleep(PERIOD_S)

# Fonction principale pour l'interface ncurses
def main():
    global barrier_angle, barrier_moving, input_register_value, t
    
    term = Terminal()

    # Démarrer le serveur Modbus dans un thread séparé
    modbus_thread = threading.Thread(target=start_modbus_server)
    modbus_thread.daemon = True
    modbus_thread.start()

    # Démarrer la mise à jour de l'angle de la barrière dans un thread séparé
    angle_thread = threading.Thread(target=update_barrier_angle)
    angle_thread.daemon = True
    angle_thread.start()

    with term.fullscreen(), term.cbreak():
        while True:
            print(term.clear())
            print(term.move_xy(0, 0) + f"Angle de la barrière: {barrier_angle:.1f}° (sens : {barrier_moving}, t : {t:.1f})")
            print(term.move_xy(0, 1) + f"Valeur brute de comptage du pont-bascule: {input_register_value}")
            print(term.move_xy(0, 3) + "Appuyez sur : 'o' ouvrir, 'c' fermer, 's' arrêter, 'w' modifier valeur comptage, 'q' quitter")

            with term.location(5, 0):
                key = term.inkey(timeout=1)
                if key == 'o':
                    barrier_moving = 1
                elif key == 'c':
                    barrier_moving = -1
                elif key == 's':
                    barrier_moving = 0
                elif key == 'w':
                    print(term.move_xy(0, 6) + "Entrez une nouvelle valeur pour l'input register (0-16777215): ")
                    new_value_str = ""
                    while True:
                        char = term.inkey()
                        if char.isdigit() or char == term.KEY_BACKSPACE:
                            if char == term.KEY_BACKSPACE:
                                new_value_str = new_value_str[:-1]
                                print(term.move_xy(0, 7) + " " * 20)  # Effacer la ligne
                                print(term.move_xy(0, 7) + new_value_str)
                            else:
                                new_value_str += char
                                print(term.move_xy(0, 7) + new_value_str)
                        else:
                            break
                    try:
                        new_value = int(new_value_str)
                        if 0 <= new_value <= 16777215:
                            update_input_register_value(new_value)
                        else:
                            print(term.move_xy(0, 8) + "Valeur invalide! Veuillez entrer un nombre entre 0 et 16777215.")
                    except ValueError:
                        print(term.move_xy(0, 8) + "Entrée invalide! Veuillez entrer un nombre valide.")
                elif key == 'q':
                    break

if __name__ == "__main__":
    main()
