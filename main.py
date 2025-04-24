import sys
from PyQt5.QtWidgets import QApplication

from src.ui.interface import MapAppWindow

if __name__ == "__main__":
    # Iniciar la aplicación con interfaz gráfica
    app = QApplication(sys.argv)
    window = MapAppWindow()
    window.show()
    sys.exit(app.exec_())
    
    
    