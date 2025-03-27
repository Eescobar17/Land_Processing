import os
import json
import tempfile
import shutil
import folium
from datetime import datetime
from folium.plugins import Draw
from PyQt5.QtWidgets import (QMainWindow, QWidget, QPushButton, QTextEdit,
                             QVBoxLayout, QHBoxLayout, QFrame, QLabel, QRadioButton,
                             QCheckBox, QLineEdit, QComboBox, QSlider, QGridLayout, QFileDialog,
                             QGroupBox, QCalendarWidget, QDialog, QDialogButtonBox)
from PyQt5.QtCore import Qt, QUrl, QDate, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal

# Importaciones del proyecto - modificadas para estructura de módulos
from src.controllers.landsat_controller import LandsatController
# from src.controllers.processing_controller import ProcessingController

from ..landsat.query import generate_landsat_query, fetch_stac_server
from ..landsat.downloader import download_images
from ..landsat.config import USGS_USERNAME, USGS_PASSWORD


class DatePickerDialog(QDialog):
    """Diálogo para seleccionar una fecha"""
    def __init__(self, parent=None, current_date=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar fecha")
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Calendario
        self.calendar = QCalendarWidget()
        layout.addWidget(self.calendar)
        


        # # Si hay una fecha actual, establecerla
        # if current_date and current_date != "dd/mm/yyyy":
        #     try:
        #         date = QDate.fromString(current_date, "dd/MM/yyyy")
        #         if date.isValid():
        #             self.calendar.setSelectedDate(date)
        #     except:
        #         pass
        

        
        # Botones
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_date(self):
        """Obtener la fecha seleccionada en formato dd/mm/yyyy"""
        date = self.calendar.selectedDate()
        return date.toString("dd/MM/yyyy")

class IndexTag(QFrame):
    """Widget personalizado para mostrar un índice seleccionado"""
    removed = pyqtSignal(str)
    
    def __init__(self, index_name):
        super().__init__()
        self.index_name = index_name
        self.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.setLineWidth(1)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(2)
        
        label = QLabel(index_name)
        layout.addWidget(label)
        
        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(16, 16)
        remove_btn.clicked.connect(self.on_remove)
        layout.addWidget(remove_btn)
        
    def on_remove(self):
        self.removed.emit(self.index_name)

class GuideDialog(QDialog):
    """Diálogo para mostrar instrucciones de uso de la aplicación"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guía de Uso")
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(self)
        
        # Título
        title_label = QLabel("Guía de Uso - Herramienta de Procesamiento Geoespacial")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)
        
        # Contenido de la guía en un QTextEdit para permitir desplazamiento
        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        guide_text.setHtml("""
        <h3>Instrucciones Generales</h3>
        <p>Esta herramienta le permite procesar datos geoespaciales de dos maneras:</p>
        <ol>
            <li><b>Importar un archivo GeoJSON/Shapefile existente</b></li>
            <li><b>Generar un polígono directamente en el mapa</b></li>
        </ol>
        
        <h3>Modo de Importación</h3>
        <ol>
            <li>Seleccione la opción "Import GeoJson/Shp File"</li>
            <li>Haga clic en el campo de texto o en el botón "..." para seleccionar un archivo</li>
            <li>Configure los parámetros adicionales según sus necesidades</li>
            <li>Presione "PROCESS" para iniciar el procesamiento</li>
        </ol>
        
        <h3>Modo de Generación de Polígono</h3>
        <ol>
            <li>Seleccione la opción "Generate Polygon"</li>
            <li>Presione el botón "Generator" para activar las herramientas de dibujo</li>
            <li>Utilice la herramienta de polígono para dibujar en el mapa</li>
            <li>Cuando termine, haga clic en "Extraer Coordenadas"</li>
            <li>Revise las coordenadas extraídas</li>
            <li>Haga clic en "Guardar Coordenadas" para exportar el polígono</li>
            <li>Configure los parámetros adicionales</li>
            <li>Presione "PROCESS" para iniciar el procesamiento</li>
        </ol>
        
        <h3>Parámetros de Configuración</h3>
        <ul>
            <li><b>Path/Row:</b> Si está habilitado, permite especificar path y row específicos</li>
            <li><b>Fechas:</b> Configure el rango de fechas para obtener imágenes satelitales</li>
            <li><b>Modo Comparativo:</b> Activar para comparar dos periodos de tiempo diferentes</li>
            <li><b>Cloud Cover:</b> Ajuste el porcentaje máximo de cobertura de nubes permitido</li>
            <li><b>Índices de Reflectancia:</b> Seleccione los índices que desea calcular (NDVI, NDWI, etc.)</li>
        </ul>
        
        <h3>Consejos</h3>
        <ul>
            <li>Para editar un polígono dibujado, utilice las herramientas de edición del mapa</li>
            <li>Procure seleccionar fechas donde haya disponibilidad de imágenes satelitales</li>
            <li>A mayor porcentaje de nubes permitido, más imágenes disponibles pero menor calidad</li>
            <li>Puede seleccionar múltiples índices de reflectancia para procesar al mismo tiempo</li>
        </ul>
        """)
        layout.addWidget(guide_text)
        
        # Botón para cerrar
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        close_button.setFixedWidth(100)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)

class ProcessThread(QThread):
    """
    Se configura un hilo aparte para evitar el bloqueo de la interfaz.
    """
    result_ready = pyqtSignal(object)  # Señal para devolver los resultados

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.landsat_controller = LandsatController(config)
        # self.processing_controller = ProcessingController(config)

    def run(self):
        """Ejecuta LandsatController"""

        try:
            gen = self.landsat_controller.fetch_data()  # Obtiene el generador
            
            while True:
                message = next(gen)  # Obtiene el siguiente mensaje
                self.result_ready.emit(message)  # Emitir mensaje en tiempo real
                self.msleep(100)  # Pequeña pausa para evitar saturar la interfaz
        
        except StopIteration as e:
            resultado = e.value  # Captura el valor de retorno

            if isinstance(resultado, tuple) and len(resultado) == 2:
                features, scenes = resultado
                print("Lista de diccionarios (scenes):", scenes)

                indices = self.config["selected_indices"]
                download_gen  = self.landsat_controller.download_data(features, scenes, indices)

                try:
                    while True:
                        message = next(download_gen)  # Obtiene el siguiente mensaje
                        self.result_ready.emit(message)  # Emitir mensaje en tiempo real
                        self.msleep(100)  # Pequeña pausa para evitar saturar la interfaz
                except StopIteration:
                    print("Descarga finalizada.")

            else:
                print("Error: La función fetch_data no retornó una tupla válida")
        
        except Exception as e:
            self.result_ready.emit(f"Error: {str(e)}")

class MapAppWindow(QMainWindow):
    """
    Ventana principal que integra el mapa interactivo y el panel de controles.
    """
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Herramienta de Procesamiento Geoespacial")
        self.setGeometry(50, 50, 1400, 800)
        
        # Variables para almacenar los valores de configuración
        self.import_mode = True
        self.generate_mode = False
        self.path_row_mode = False
        self.path_value = ""
        self.row_value = ""
        self.diff_date_enabled = False
        self.cloud_cover_value = 50
        self.platform_value = "LANDSAT_8"
        self.imported_file_path = ""
        self.generated_file_path = ""
        self.min_area_value = 10

        # Variable booleana para activar el panel de instrucciones del mapa
        self.show_instructions = False
        
        # Fechas (inicializadas con formato)
        self.start_date = "dd/mm/yyyy"
        self.end_date = "dd/mm/yyyy"
        self.diff_start_date = "dd/mm/yyyy"
        self.diff_end_date = "dd/mm/yyyy"
        
        # Lista para almacenar los índices seleccionados
        self.selected_indices = []
        
        # Almacenar las coordenadas extraídas del mapa
        self.polygons = []

        # Almacenar los datos GeoJSON originales
        self.geojson_data = None
        
        # Widget principal y layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        
        # Crear los paneles
        self.setup_control_panel()
        self.setup_map_panel()
        
        # Configurar herramientas de dibujo
        self.draw_options = {
            'polyline': False,
            'rectangle': False,
            'circle': False,
            'marker': False,
            'circlemarker': False,
            'polygon': False
        }

        self.edit_options = {
            'edit': False,
            'remove': False
        }

        # Crear y cargar el mapa
        self.html_file = self.create_interactive_map()
        self.web_view.load(QUrl.fromLocalFile(self.html_file))
           
    def add_tooltips(self):
        """Añade tooltips informativos a los widgets de la interfaz"""
        
        # Tooltips para Importación
        self.import_radio.setToolTip("Seleccione esta opción para importar un archivo GeoJSON o Shapefile existente")
        self.search_entry.setToolTip("Haga clic aquí para seleccionar un archivo GeoJSON o Shp")

        # Tooltips para Generador
        self.generate_radio.setToolTip("Seleccione esta opción para dibujar un polígono directamente en el mapa")
        
        # Tooltips para Path/Row
        self.path_row_radio.setToolTip("Active esta opción para filtrar imágenes por Path/Row específicos")
        self.path_entry.setToolTip("Introduzca el número de Path (ruta) de la imagen satelital")
        self.row_entry.setToolTip("Introduzca el número de Row (fila) de la imagen satelital")
        
        # Tooltips para fechas
        self.start_date_entry.setToolTip("Fecha de inicio del periodo de búsqueda (dd/mm/yyyy)")
        self.end_date_entry.setToolTip("Fecha de fin del periodo de búsqueda (dd/mm/yyyy)")
        self.diff_date_check.setToolTip("Active para comparar dos periodos de tiempo diferentes")
        self.diff_start_date_entry.setToolTip("Fecha de inicio del periodo de comparación (dd/mm/yyyy)")
        self.diff_end_date_entry.setToolTip("Fecha de fin del periodo de comparación (dd/mm/yyyy)")
        
        # Tooltips para cloud cover
        self.cloud_slider.setToolTip("Ajuste el porcentaje máximo permitido de cobertura de nubes (0-100%)")
        
        # Tooltips para platform e índices
        self.platform_combo.setToolTip("Seleccione la plataforma satelital a utilizar")
        self.reflectance_combo.setToolTip("Seleccione los índices de reflectancia a calcular:\n"
                                          "NDVI - Índice de Vegetación de Diferencia Normalizada\n"
                                          "NDWI - Índice de Agua de Diferencia Normalizada\n"
                                          "NDSI - Índice de Nieve de Diferencia Normalizada\n"
                                          "BSI - Índice de Suelo Desnudo\n"
                                          "LST - Temperatura de la Superficie Terrestre")
        



        # Tooltips para botones de acción
        process_button = self.findChild(QPushButton, name="process_button")  # Necesitamos añadir objectName al botón
        if process_button:
            process_button.setToolTip("Iniciar el procesamiento con los parámetros configurados")

        self.save_button.setToolTip("Guardar las coordenadas extraídas en archivos JSON y GeoJSON")
        
        # Buscar el botón de extraer coordenadas y agregarle un tooltip
        extract_buttons = [btn for btn in self.findChildren(QPushButton) if btn.text() == "Extraer Coordenadas"]
        if extract_buttons:
            extract_buttons[0].setToolTip("Extraer las coordenadas de los polígonos dibujados en el mapa")

    def setup_control_panel(self):
        """Configura el panel izquierdo con controles"""
        # Panel de control izquierdo
        self.control_panel = QFrame()
        self.control_panel.setFrameStyle(QFrame.Box | QFrame.Sunken)
        self.control_panel_layout = QVBoxLayout(self.control_panel)
        
        # Panel de opciones
        options_panel = QWidget()
        options_layout = QGridLayout(options_panel)
        options_layout.setSpacing(5)
        options_layout.setContentsMargins(0, 0, 0, 0)

        # ----------------------------
        # Primera fila: Import GeoJson
        # ----------------------------
        
        hbox1 = QHBoxLayout()
        hbox1.setContentsMargins(0, 0, 0, 0)
        hbox1.setSpacing(5)

        self.import_radio = QRadioButton("Importar archivo GeoJson/Shp")
        self.import_radio.setChecked(True)
        self.import_radio.toggled.connect(self.toggle_import_mode)
        hbox1.addWidget(self.import_radio)

        self.search_entry = QLineEdit()
        self.search_entry.setCursor(QCursor(Qt.PointingHandCursor))
        self.search_entry.setStyleSheet("background-color: #F0F0F0;")
        self.search_entry.setReadOnly(True)  # Hacer el campo de solo lectura
        self.search_entry.mousePressEvent = lambda e: self.import_file()
        self.search_entry.setFixedWidth(120)
        hbox1.addWidget(self.search_entry)

        self.browse_button = QPushButton("...")
        self.browse_button.setFixedWidth(30)
        self.browse_button.clicked.connect(self.import_file)
        hbox1.addWidget(self.browse_button)
        
        hbox1.addStretch(1)
        options_layout.addLayout(hbox1, 0, 0)

        # ------------------------------
        # Segunda fila: Generate Polygon
        # ------------------------------

        hbox2 = QHBoxLayout()
        hbox2.setContentsMargins(0, 0, 0, 0)
        hbox2.setSpacing(5)

        self.generate_radio = QRadioButton("Generar Polígono")
        self.generate_radio.toggled.connect(self.toggle_generate_mode)
        hbox2.addWidget(self.generate_radio)

        self.generator_textbox = QLineEdit()
        self.generator_textbox.setFixedWidth(120)
        self.generator_textbox.setReadOnly(True)
        self.generator_textbox.setPlaceholderText("GeoJSON...")
        self.generator_textbox.setStyleSheet("background-color: #F0F0F0;")
        hbox2.addWidget(self.generator_textbox)

        guide_button = QPushButton("GUÍA")
        guide_button.setFixedWidth(100)
        guide_button.clicked.connect(self.show_guide)
        hbox2.addWidget(guide_button)

        hbox2.addStretch(1)
        options_layout.addLayout(hbox2, 1, 0)

        # ------------------------
        # Tercera fila: Path y Row
        # ------------------------

        path_row_layout = QHBoxLayout()
        path_row_layout.setContentsMargins(0, 0, 0, 0)
        path_row_layout.setSpacing(5)

        self.path_row_radio = QRadioButton("Path:")
        self.path_row_radio.toggled.connect(self.toggle_path_row)
        path_row_layout.addWidget(self.path_row_radio)

        self.path_entry = QLineEdit()
        self.path_entry.setFixedWidth(70)
        self.path_entry.setEnabled(False)
        path_row_layout.addWidget(self.path_entry)

        path_row_layout.addWidget(QLabel("Row:"))

        self.row_entry = QLineEdit()
        self.row_entry.setFixedWidth(70)
        self.row_entry.setEnabled(False)
        path_row_layout.addWidget(self.row_entry)

        path_row_layout.addStretch(1)
        options_layout.addLayout(path_row_layout, 2, 0)
        
        # ----------------------------

        # Añadir panel de opciones al layout izquierdo
        self.control_panel_layout.addWidget(options_panel)
        
        # Panel de parámetros
        params_frame = QGroupBox("Parámetros")
        params_layout = QVBoxLayout(params_frame)
        
        # Date selection frames
        dates_frame = QWidget()
        dates_layout = QGridLayout(dates_frame)
        dates_layout.setContentsMargins(0, 0, 0, 0)
        dates_layout.setSpacing(5)
        
        # Checkbox "Comparativo" - En la primera fila, abarcando ambas columnas
        self.diff_date_check = QCheckBox("Comparativo")
        self.diff_date_check.toggled.connect(self.toggle_diff_date)
        dates_layout.addWidget(self.diff_date_check, 0, 2, 1, 1, Qt.AlignLeft)
        
        # Primera columna - Fechas principales
        dates_layout.addWidget(QLabel("Fecha Inicial:"), 1, 0)
        self.start_date_entry = QLineEdit(self.start_date)
        self.start_date_entry.setFixedWidth(100)
        self.start_date_entry.setReadOnly(True)
        date_entry_layout1 = QHBoxLayout()
        date_entry_layout1.addWidget(self.start_date_entry)
                
        # Botón de calendario para Fecha Inicial
        start_date_picker = QPushButton("📅")
        start_date_picker.setFixedWidth(30)
        start_date_picker.clicked.connect(lambda: self.pick_date(self.start_date_entry))
        date_entry_layout1.addWidget(start_date_picker)
        date_entry_layout1.addStretch()
        dates_layout.addLayout(date_entry_layout1, 1, 1)
        
        dates_layout.addWidget(QLabel("Fecha Final:"), 2, 0)
        self.end_date_entry = QLineEdit(self.end_date)
        self.end_date_entry.setFixedWidth(100)
        self.end_date_entry.setReadOnly(True)
        date_entry_layout2 = QHBoxLayout()
        date_entry_layout2.addWidget(self.end_date_entry)
                
        # Botón de calendario para Fecha Final
        end_date_picker = QPushButton("📅")
        end_date_picker.setFixedWidth(30)
        end_date_picker.clicked.connect(lambda: self.pick_date(self.end_date_entry))
        date_entry_layout2.addWidget(end_date_picker)
        date_entry_layout2.addStretch()
        dates_layout.addLayout(date_entry_layout2, 2, 1)
        
        # Segunda columna - Fechas comparativas
        dates_layout.addWidget(QLabel("Fecha Inicial Alt.:"), 1, 2)
        self.diff_start_date_entry = QLineEdit(self.diff_start_date)
        self.diff_start_date_entry.setFixedWidth(100)
        self.diff_start_date_entry.setReadOnly(True)
        self.diff_start_label = dates_layout.itemAtPosition(1, 2).widget()  # Guardar referencia
        
        date_entry_layout3 = QHBoxLayout()
        date_entry_layout3.addWidget(self.diff_start_date_entry)
                
        # Botón de calendario para Diff Start Date
        self.diff_start_date_picker = QPushButton("📅")
        self.diff_start_date_picker.setFixedWidth(30)
        self.diff_start_date_picker.clicked.connect(lambda: self.pick_date(self.diff_start_date_entry))
        date_entry_layout3.addWidget(self.diff_start_date_picker)
        date_entry_layout3.addStretch()
        dates_layout.addLayout(date_entry_layout3, 1, 3)
        
        dates_layout.addWidget(QLabel("Fecha Final Alt.:"), 2, 2)
        self.diff_end_date_entry = QLineEdit(self.diff_end_date)
        self.diff_end_date_entry.setFixedWidth(100)
        self.diff_end_date_entry.setReadOnly(True)
        self.diff_end_label = dates_layout.itemAtPosition(2, 2).widget()  # Guardar referencia
        
        date_entry_layout4 = QHBoxLayout()
        date_entry_layout4.addWidget(self.diff_end_date_entry)
                
        # Botón de calendario para Diff End Date
        self.diff_end_date_picker = QPushButton("📅")
        self.diff_end_date_picker.setFixedWidth(30)
        self.diff_end_date_picker.clicked.connect(lambda: self.pick_date(self.diff_end_date_entry))
        date_entry_layout4.addWidget(self.diff_end_date_picker)
        date_entry_layout4.addStretch()
        dates_layout.addLayout(date_entry_layout4, 2, 3)
        
        params_layout.addWidget(dates_frame)
        
        # Inicialmente deshabilitar los widgets comparativos
        self.toggle_diff_date()
        
        # Cloud Cover slider
        cloud_frame = QWidget()
        cloud_layout = QHBoxLayout(cloud_frame)
        cloud_layout.setContentsMargins(0, 0, 0, 0)
        
        cloud_layout.addWidget(QLabel("Cobertura de Nubes:"))
        self.cloud_slider = QSlider(Qt.Horizontal)
        self.cloud_slider.setRange(0, 100)
        self.cloud_slider.setValue(self.cloud_cover_value)
        self.cloud_slider.valueChanged.connect(self.update_cloud_cover)
        cloud_layout.addWidget(self.cloud_slider)
        
        # Etiqueta para mostrar el valor actual
        self.cloud_value_label = QLabel(f"{self.cloud_cover_value}%")
        cloud_layout.addWidget(self.cloud_value_label)
        
        params_layout.addWidget(cloud_frame)
        
        # Platform selector
        platform_frame = QWidget()
        platform_layout = QHBoxLayout(platform_frame)
        platform_layout.setContentsMargins(0, 0, 0, 0)
        platform_layout.setSpacing(5)

        platform_layout.addWidget(QLabel("Plataforma:"))
        self.platform_combo = QComboBox()
        self.platform_combo.addItem("LANDSAT_8")
        self.platform_combo.setFixedWidth(120)  # Ancho fijo para controlar el tamaño
        platform_layout.addWidget(self.platform_combo)
        platform_layout.addStretch(1)  # Añadir stretch para empujar todo a la izquierda

        params_layout.addWidget(platform_frame)

        # Reflectance indices con sistema de selección y visualización
        reflectance_frame = QWidget()
        reflectance_layout = QHBoxLayout(reflectance_frame)
        reflectance_layout.setContentsMargins(0, 0, 0, 0)
        reflectance_layout.setSpacing(5)

        reflectance_layout.addWidget(QLabel("Índices de\nReflectancia:"))

        # Lista ordenada alfabéticamente con mensaje por defecto
        self.reflectance_combo = QComboBox()
        self.reflectance_combo.addItem("Seleccione el índice")
        reflectance_values = ["BSI", "LST", "NDSI", "NDVI", "NDWI"]
        self.reflectance_combo.addItems(reflectance_values)
        self.reflectance_combo.currentIndexChanged.connect(self.add_index)
        self.reflectance_combo.setFixedWidth(150)  # Ancho fijo para controlar el tamaño
        reflectance_layout.addWidget(self.reflectance_combo)
        reflectance_layout.addStretch(1)  # Añadir stretch para empujar todo a la izquierda

        params_layout.addWidget(reflectance_frame)
        
        # Frame para mostrar los índices seleccionados como botones
        self.indices_container = QWidget()
        self.indices_container_layout = QHBoxLayout(self.indices_container)
        self.indices_container_layout.setAlignment(Qt.AlignLeft)
        self.indices_container_layout.setContentsMargins(0, 0, 0, 0)
        
        params_layout.addWidget(self.indices_container)
        
        # Panel de resultados
        results_frame = QGroupBox("Resultados")
        results_layout = QVBoxLayout(results_frame)
        
        # Panel de texto para mostrar resultados
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        results_layout.addWidget(self.results_text)
        
        # Botón para extraer coordenadas
        self.extract_button = QPushButton("Extraer Coordenadas")
        self.extract_button.clicked.connect(self.extract_coordinates)
        self.extract_button.setEnabled(False)
        results_layout.addWidget(self.extract_button)
        
        # Botón para guardar coordenadas
        self.save_button = QPushButton("Exportar Coordenadas")
        self.save_button.clicked.connect(self.save_coordinates)
        self.save_button.setEnabled(False)  # Deshabilitado hasta que se extraigan coordenadas
        results_layout.addWidget(self.save_button)
        
        # Process buttons
        process_frame = QWidget()
        process_layout = QHBoxLayout(process_frame)
        
        process_button = QPushButton("PROCESAR DATOS")
        process_button.setObjectName("process_button")  # Añadir objectName para poder encontrarlo luego
        process_button.setFixedSize(150, 50)
        process_button.setStyleSheet("font-weight: bold; font-size: 14px;")
        process_button.clicked.connect(self.process_data)
        process_layout.addWidget(process_button)
        process_layout.addStretch()
        
        results_layout.addWidget(process_frame)
        
        # Añadir componentes al panel izquierdo
        self.control_panel_layout.addWidget(params_frame)
        self.control_panel_layout.addWidget(results_frame)
        self.add_tooltips()
        
        # Añadir el panel de control al layout principal
        self.layout.addWidget(self.control_panel, 1)
        
    def setup_map_panel(self):
        """Configura el panel derecho con el mapa interactivo"""
        # Panel de mapa derecho
        self.map_panel = QFrame()
        self.map_panel.setFrameStyle(QFrame.Box | QFrame.Sunken)
        self.map_panel_layout = QVBoxLayout(self.map_panel)
        
        # Componente web para mostrar el mapa de folium
        self.web_view = QWebEngineView()
        self.map_panel_layout.addWidget(self.web_view)
        
        # Añadir el panel de mapa al layout principal
        self.layout.addWidget(self.map_panel, 2)
    
    def create_interactive_map(self):
        """
        Crea un mapa de Folium con herramientas de dibujo y lo guarda como HTML.
        
        Returns:
            str: Ruta al archivo HTML del mapa.
        """
        # Crear mapa centrado en Colombia
        m = folium.Map(location=[4.6097, -74.0817], zoom_start=6)

        # Crear una capa para almacenar los elementos dibujados
        draw_items = folium.FeatureGroup(name="Drawn polygons")
        m.add_child(draw_items)
        
        # Añadir control de dibujo referenciando la capa donde se guardarán los elementos
        draw = Draw(
            export=False,
            draw_options=self.draw_options,
            edit_options=self.edit_options,
            feature_group=draw_items
        )
        m.add_child(draw)
        
        # Añadir JavaScript para exponer la capa de dibujo al objeto window
        m.get_root().html.add_child(folium.Element(
            """
            <script>
            document.addEventListener('DOMContentLoaded', function() {
                // Esperar a que el mapa se cargue
                setTimeout(function() {
                    // Exponer las capas de dibujo globalmente
                    var drawControl = document.querySelector('.leaflet-draw');
                    if (drawControl) {
                        // Buscar la capa de elementos dibujados
                        var map = Object.values(window).find(v => v && v._container && v._container.classList && v._container.classList.contains('leaflet-container'));
                        if (map) {
                            // Exponer drawnItems globalmente
                            window.map = map;
                            window.drawnItems = Array.from(Object.values(map._layers)).find(
                                layer => layer && layer.options && layer.options.name === "Drawn polygons"
                            );
                            console.log("Capa de dibujo expuesta globalmente:", window.drawnItems);
                        }
                    }
                }, 1000);
            });
            </script>
            """
        ))
        
        # Añadir panel de instrucciones
        instructions_html = """
        <div style="position: fixed;
                    bottom: 20px;
                    left: 20px;
                    width: 300px;
                    padding: 5px;
                    background-color: white;
                    z-index: 9999;
                    border-radius: 5px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.3);">
            <h4>Instrucciones:</h4>
            <ol>
                <li>Usa la herramienta de polígono para dibujar en el mapa</li>
                <li>Cuando termines, haz clic en "Extraer Coordenadas" en el panel izquierdo</li>
                <li>Revisa las coordenadas mostradas</li>
                <li>Haz clic en "Guardar Coordenadas" para exportarlas</li>
            </ol>
        </div>
        """

        if self.show_instructions:
            m.get_root().html.add_child(folium.Element(instructions_html))
        
        # Añadir JavaScript para recuperar los polígonos dibujados
        js = """
        <script>
        // Función para recuperar todos los polígonos dibujados
        function getDrawnItems() {
            let drawnItems = { "type": "FeatureCollection", "features": [] };
            
            // Acceder directamente a las capas de dibujo a través del objeto global
            if (typeof window.drawnItems !== 'undefined') {
                drawnItems = window.drawnItems.toGeoJSON();
            } else {
                // Buscar las capas de dibujo en el DOM
                document.querySelectorAll('.leaflet-overlay-pane path').forEach(function(path) {
                    if (path._drawnByLeaflet) {
                        let layer = path._drawnByLeaflet;
                        if (layer && typeof layer.toGeoJSON === 'function') {
                            drawnItems.features.push(layer.toGeoJSON());
                        }
                    }
                });
            }
            
            // Si no hay características, crear un objeto predeterminado
            if (!drawnItems || !drawnItems.features) {
                drawnItems = {
                    "type": "FeatureCollection",
                    "features": []
                };
            }
            
            return JSON.stringify(drawnItems);
        }
        
        // Exponer función al objeto window para que pueda ser llamada desde PyQt
        window.getDrawnPolygons = function() {
            return getDrawnItems();
        }
        </script>
        """
        m.get_root().html.add_child(folium.Element(js))
        
        # Guardar mapa como archivo HTML temporal
        html_file = os.path.join(tempfile.gettempdir(), "mapa_poligono.html")
        m.save(html_file)
        
        return html_file
        
    def extract_coordinates(self):
        """
        Extrae las coordenadas de los polígonos dibujados en el mapa.
        """
        self.results_text.clear()
        self.results_text.append("Intentando extraer coordenadas de los polígonos dibujados...")
        
        # Código JS más detallado para diagnosticar el problema
        js_code = """
        (function() {
            // Buscar todas las capas de dibujo en el mapa
            var map = null;
            var drawnItems = null;
            
            // Intentar encontrar el objeto mapa
            for (var key in window) {
                if (window[key] && 
                    typeof window[key] === 'object' && 
                    window[key]._container && 
                    window[key]._container.classList && 
                    window[key]._container.classList.contains('leaflet-container')) {
                    map = window[key];
                    break;
                }
            }
            
            if (!map) {
                return JSON.stringify({
                    "error": "No se pudo encontrar el objeto mapa",
                    "type": "FeatureCollection",
                    "features": []
                });
            }
            
            // Buscar las capas de dibujo
            var allLayers = {};
            for (var layerId in map._layers) {
                var layer = map._layers[layerId];
                allLayers[layerId] = {
                    "type": layer.type,
                    "hasToGeoJSON": typeof layer.toGeoJSON === 'function'
                };
                
                // Si es una capa de tipo FeatureGroup, podría contener los polígonos
                if (layer instanceof L.FeatureGroup) {
                    drawnItems = layer;
                }
            }
            
            // Si encontramos un grupo de características, extraer como GeoJSON
            if (drawnItems) {
                try {
                    return JSON.stringify(drawnItems.toGeoJSON());
                } catch (e) {
                    return JSON.stringify({
                        "error": "Error al convertir a GeoJSON: " + e.message,
                        "type": "FeatureCollection",
                        "features": []
                    });
                }
            }
            
            // Si no encontramos el grupo, devolver información de diagnóstico
            return JSON.stringify({
                "error": "No se encontró la capa de dibujo",
                "mapInfo": {
                    "layerCount": Object.keys(map._layers).length,
                    "layers": allLayers
                },
                "type": "FeatureCollection",
                "features": []
            });
        })();
        """
        
        # Ejecutar JavaScript para obtener los polígonos dibujados
        self.web_view.page().runJavaScript(js_code, self.process_javascript_result)
    
    def process_javascript_result(self, result):
        """
        Procesa el resultado del JavaScript y extrae las coordenadas.
        
        Args:
            result (str): Resultado en formato GeoJSON.
        """
        try:
            self.results_text.clear()
            
            # Verificar si el resultado es None o vacío
            if result is None or result == "":
                self.results_text.append("No se detectaron polígonos dibujados en el mapa.")
                self.results_text.append("Por favor, dibuja al menos un polígono usando la herramienta de dibujo y vuelve a intentarlo.")
                return
                
            # Intentar analizar el JSON
            # self.results_text.append(f"Datos recibidos: {result[:100]}...")
            data = json.loads(result)
            
            # Guardar los datos GeoJSON originales para exportarlos después
            self.geojson_data = data
            
            # Verificar si hay características en el GeoJSON
            if 'features' not in data or len(data['features']) == 0:
                self.results_text.append("No se encontraron polígonos en los datos extraídos.")
                self.results_text.append("Por favor, dibuja al menos un polígono usando la herramienta de dibujo y vuelve a intentarlo.")
                return
                
            # Extraer coordenadas
            self.polygons = self.extract_coordinates_from_geojson(data)
            
            if not self.polygons:
                self.results_text.append("No se pudieron extraer coordenadas válidas de los polígonos dibujados.")
                return
                
            # Mostrar las coordenadas
            self.results_text.append("Coordenadas extraídas:")
            
            for i, polygon in enumerate(self.polygons):
                self.results_text.append(f"\nPolígono {i+1}:")
                for j, coord in enumerate(polygon[:-1]):  # Excluir la última coordenada
                    self.results_text.append(f"  Punto {j+1}: Latitud={coord[0]}, Longitud={coord[1]}")

            
            # Habilitar el botón de guardar
            self.save_button.setEnabled(True)
            
            # # También, si estamos en modo import, actualizar el campo de búsqueda
            # if self.import_mode:
            #     self.search_entry.setText("Polígono dibujado manualmente")
            
        except Exception as e:
            self.results_text.append(f"Error al procesar el resultado: {str(e)}")
            self.results_text.append("Detalles del error para depuración:")
            import traceback
            self.results_text.append(traceback.format_exc())
    
    def extract_coordinates_from_geojson(self, data):
        """
        Extrae las coordenadas de polígonos desde un objeto GeoJSON.
        
        Args:
            data (dict): Objeto GeoJSON.
            
        Returns:
            list: Lista de polígonos, donde cada polígono es una lista de coordenadas [lat, lon].
        """
        polygons = []
        
        # Procesar las geometrías en el GeoJSON
        if 'features' in data:
            for feature in data['features']:
                geometry = feature.get('geometry', {})
                
                if geometry.get('type') == 'Polygon':
                    # Las coordenadas externas del polígono (primer anillo)
                    coords = geometry['coordinates'][0]
                    # Convertir [lon, lat] a [lat, lon]
                    polygon = [[coord[1], coord[0]] for coord in coords]
                    polygons.append(polygon)
        
        return polygons
    
    def save_coordinates(self):
        """
        Guarda las coordenadas extraídas en archivos JSON y GeoJSON.
        """
        if not self.polygons:
            self.results_text.append("No hay coordenadas para guardar.")
            return
        
        # Obtener la ruta base del proyecto (asumiendo desde LAND_PROCESSING/src/)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))

        # ---------------------
        # Exportar archivo JSON
        # ---------------------

        save_dir = os.path.normpath(os.path.join(base_dir, "data/exports/"))

        # Crear la carpeta si no existe
        os.makedirs(save_dir, exist_ok=True)

        # Guardar en formato JSON personalizado
        output_file_json = f"{save_dir}coordenadas_poligono.json"
        with open(output_file_json, 'w') as f:
            json.dump({"polygons": self.polygons}, f, indent=4)


        # ---------------------
        # Exportar archivo GEOJSON
        # ---------------------

        save_dir = os.path.normpath(os.path.join(base_dir, "data/temp/source/"))

        # Limpiar la carpeta eliminando todo su contenido
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir)  # Elimina la carpeta y su contenido

        # Crear la carpeta si no existe
        os.makedirs(save_dir, exist_ok=True)

        # Guardar en formato GeoJSON estándar
        output_file_geojson = f"{save_dir}source_file.geojson"

        # Obtener la ruta absoluta del archivo GeoJSON (para facilitar su uso en otros scripts)
        abs_path_geojson = os.path.abspath(output_file_geojson)
        
        # Verificar si tenemos los datos originales de GeoJSON
        if self.geojson_data:
            with open(output_file_geojson, 'w') as f:
                json.dump(self.geojson_data, f, indent=4)
            self.results_text.append(f"\nCoordenadas guardadas en {output_file_json} y en formato GeoJSON en {output_file_geojson}")

            # Si estamos en modo generate, actualizar la caja de texto con la ruta del archivo
            if self.generate_mode:
                self.generator_textbox.setText(os.path.basename(output_file_geojson))
                self.generator_textbox.setToolTip(abs_path_geojson)  # Mostrar ruta completa como tooltip
                
                # Almacenar la ruta del archivo para usarla en process_data
                self.generated_file_path = abs_path_geojson
        else:
            # Crear un GeoJSON a partir de las coordenadas extraídas
            geojson = {
                "type": "FeatureCollection",
                "features": []
            }
            
            for polygon in self.polygons:
                # Convertir de [lat, lon] a [lon, lat] para GeoJSON
                coords = [[coord[1], coord[0]] for coord in polygon]
                
                # Cerrar el polígono si no está cerrado (primer punto = último punto)
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                
                feature = {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                }
                geojson["features"].append(feature)
            
            with open(output_file_geojson, 'w') as f:
                json.dump(geojson, f, indent=4)
            
            self.results_text.append(f"\nCoordenadas guardadas en {output_file_json} y en formato GeoJSON en {output_file_geojson}")
            
            # Si estamos en modo generate, actualizar la caja de texto con la ruta del archivo
            if self.generate_mode:
                self.generator_textbox.setText(os.path.basename(output_file_geojson))
                self.generator_textbox.setToolTip(abs_path_geojson)  # Mostrar ruta completa como tooltip
                
                # Almacenar la ruta del archivo para usarla en process_data
                self.generated_file_path = abs_path_geojson
            
            # Si estamos en modo import, actualizar el campo de búsqueda con la ruta del archivo
            if self.import_mode:
                self.imported_file_path = abs_path_geojson
                self.search_entry.setText(os.path.basename(output_file_geojson))

    def show_guide(self):
        """Muestra la ventana de guía"""
        guide_dialog = GuideDialog(self)
        guide_dialog.exec_()

    def toggle_import_mode(self, checked):
        """Cambia entre modo import y generate"""
        self.import_mode = checked
        self.search_entry.setEnabled(checked)
        self.browse_button.setEnabled(checked)
        self.save_button.setEnabled(False)
        self.extract_button.setEnabled(False)
    
    def toggle_generate_mode(self, checked):
        """Cambia entre modo generate e import"""
        self.generate_mode = checked

        # Si se activa el modo de generación, habilitar herramientas de dibujo
        if checked:
            self.draw_options['polygon'] = True
            self.edit_options['remove'] = True
            self.extract_button.setEnabled(True)  # Activar el botón de extraer coordenadas
            self.show_instructions = True
        else:
            self.draw_options['polygon'] = False
            self.edit_options['remove'] = False
            self.extract_button.setEnabled(False)
            self.show_instructions = False
        
        # Actualizar el mapa con las nuevas herramientas
        self.update_map()
    
    def toggle_path_row(self, checked):
        """Habilita/deshabilita los campos de path/row"""
        self.path_row_mode = checked
        self.path_entry.setEnabled(checked)
        self.row_entry.setEnabled(checked)
        self.save_button.setEnabled(False)
        self.extract_button.setEnabled(False)
    
    def toggle_diff_date(self):
        """Habilita/deshabilita los campos de fechas comparativas"""
        enabled = self.diff_date_check.isChecked()
        self.diff_date_enabled = enabled
        
        # Habilitar/deshabilitar widgets
        self.diff_start_label.setEnabled(enabled)
        self.diff_start_date_entry.setEnabled(enabled)
        self.diff_start_date_picker.setEnabled(enabled)
        self.diff_end_label.setEnabled(enabled)
        self.diff_end_date_entry.setEnabled(enabled)
        self.diff_end_date_picker.setEnabled(enabled)
    
    def update_cloud_cover(self, value):
        """Actualiza el valor del cloud cover y la etiqueta"""
        self.cloud_cover_value = value
        self.cloud_value_label.setText(f"{value}%")
    
    def pick_date(self, entry_widget):
        """Muestra un calendario en un diálogo para seleccionar una fecha"""
        current_date = entry_widget.text()
        dialog = DatePickerDialog(self, current_date)
        
        if dialog.exec_() == QDialog.Accepted:
            selected_date = dialog.get_date()
            entry_widget.setText(selected_date)
    
    def add_index(self):
        """Añade un índice seleccionado a la lista"""
        index = self.reflectance_combo.currentText()
        
        # Verificar que no esté ya en la lista, que no esté vacío y que no sea el mensaje por defecto
        if (index and 
            index not in self.selected_indices and 
            index != "Seleccione el índice"):
            
            self.selected_indices.append(index)
            self.create_index_tags()
            
        # Restablecer el combobox al valor por defecto
        self.reflectance_combo.setCurrentIndex(0)
    
    def remove_index(self, index):
        """Elimina un índice de la lista"""
        if index in self.selected_indices:
            self.selected_indices.remove(index)
            self.create_index_tags()
    
    def create_index_tags(self):
        """Crea los tags visuales para los índices seleccionados"""
        # Limpiar el contenedor de índices
        for i in reversed(range(self.indices_container_layout.count())):
            widget = self.indices_container_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
        
        # Recrear los tags para cada índice seleccionado
        for index in self.selected_indices:
            tag = IndexTag(index)
            tag.removed.connect(self.remove_index)
            self.indices_container_layout.addWidget(tag)
    
    def import_file(self):
        """Abre un diálogo para seleccionar un archivo GeoJSON o SHP"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo GeoJSON o Shapefile",
            "",
            "GeoJSON files (*.geojson);;Shapefile (*.shp)"
        )
        
        if file_path:
            # Obtener la ruta base del proyecto (asumiendo desde LAND_PROCESSING/src/)
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
            save_dir = os.path.join(base_dir, "data/temp/source/")

            # Limpiar la carpeta eliminando todo su contenido
            if os.path.exists(save_dir):
                shutil.rmtree(save_dir)  # Elimina la carpeta y su contenido

            # Crear la carpeta si no existe
            os.makedirs(save_dir, exist_ok=True)

            # Obtener la extensión del archivo original
            _, file_extension = os.path.splitext(file_path)

            new_name = f"source_file{file_extension}"

            # Definir la nueva ruta donde se guardará el archivo
            new_path = os.path.normpath(os.path.join(save_dir, new_name))

            # Copiar el archivo a la nueva ubicación con el nuevo nombre
            shutil.copy(file_path, new_path)

            # Actualizar la variable y el campo de texto con la nueva ruta
            self.imported_file_path = new_path
            self.search_entry.setText(os.path.basename(file_path))
            self.results_text.append(f"Archivo importado y guardado en: {new_path}")
    
    def open_polygon_generator(self):
        """Abre la interfaz de generación de polígonos"""
        self.results_text.append("Utilizando el generador de polígonos integrado")
        self.extract_button.setEnabled(True) # Activa el botón Extraer Coordenadas
        
        # Cambiar valores de polygon y remove y actualiza el mapa
        self.draw_options['polygon'] = True
        self.edit_options['remove'] = True
        self.update_map()

    def update_map(self):
        """Regenera el mapa."""

        # Regenerar el mapa
        self.html_file = self.create_interactive_map()
        
        # Recargar el mapa en la interfaz
        self.web_view.load(QUrl.fromLocalFile(self.html_file))

    def process_data(self):
        """Procesa los datos basados en la configuración actual"""
        
        def validar_fecha(fecha):
            """Valida que la fecha tenga el formato correcto (YYYY-MM-DD)"""
            try:
                if fecha and fecha != "dd/mm/yyyy":
                    return datetime.strptime(fecha, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
            return ""  # Retorna vacío si es inválida

        # Obtener valores de las entradas con validación
        start_date = validar_fecha(self.start_date_entry.text())
        end_date = validar_fecha(self.end_date_entry.text())
        diff_start_date = validar_fecha(self.diff_start_date_entry.text())
        diff_end_date = validar_fecha(self.diff_end_date_entry.text())

        # Obtener valores actualizados
        config = {
            "file_path": "../../data/temp/source/source_file.*",
            "import_mode": getattr(self, "import_mode", False),  
            "generate_mode": getattr(self, "generate_mode", False),
            "path_row_mode": getattr(self, "path_row_mode", False),
            "path": str(self.path_entry.text()).zfill(3),
            "row": str(self.row_entry.text()).zfill(3),
            "start_date": start_date,
            "end_date": end_date,
            "diff_date_enabled": getattr(self, "diff_date_enabled", False),
            "diff_start_date": diff_start_date,
            "diff_end_date": diff_end_date,
            "cloud_cover": getattr(self, "cloud_cover_value", 0),
            "selected_indices": getattr(self, "selected_indices", []),
            "imported_file": os.path.basename(self.imported_file_path) if getattr(self, "imported_file_path", "") else "",
            "platform": [self.platform_combo.currentText()],
            "collections": ["landsat-c2l2-sr"],
            "limit": 100
        }

        # Guardar configuración en JSON
        config_file = "process_config.json"
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el archivo de configuración: {str(e)}")
            return  # Detener el proceso si hay error

        # ------------------------------
        # Mostrar resumen de la configuración
        # ------------------------------
        resumen = [
            "=== Procesando datos ===",
            f"Configuración guardada en {config_file}",
            "\nResumen de configuración:",
            f"- Modo: {'Importar archivo' if config['import_mode'] else 'Generar polígono' if config['generate_mode'] else 'Seleccionar Path/Row'}",
            f"- Fechas: {config['start_date']} a {config['end_date']}",
            f"- Fechas comparativas: {config['diff_start_date']} a {config['diff_end_date']}" if config['diff_date_enabled'] else "- No hay comparación de fechas",
            f"- Cobertura de nubes: {config['cloud_cover']}%",
            f"- Plataformas: {', '.join(config['platform'])}",
            f"- Índices seleccionados: {', '.join(config['selected_indices'])}" if config['selected_indices'] else "- No se seleccionaron índices de reflectancia",
            f"- Archivo importado: {config['imported_file']}" if config['import_mode'] and config['imported_file'] else "- No se ha importado ningún archivo",
            "\n=== Iniciando procesamiento de datos ==="
        ]

        self.results_text.clear()
        self.results_text.append("\n".join(resumen))

        # ------------------------------------------
        # Procesar datos mediante hilo independiente
        # ------------------------------------------

        self.thread = ProcessThread(config)
        self.thread.result_ready.connect(self.handle_result)
        self.thread.start()

    def handle_result(self, result):
        """Muestra un mensaje cuando finaliza el proceso"""
        # QMessageBox.information(self, "Proceso finalizado", f"Datos obtenidos: {result}")
        self.results_text.append(result)