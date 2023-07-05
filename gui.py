import os, sys, json, requests
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QAbstractItemView, QPushButton, QGroupBox, QRadioButton, QSpacerItem, QCheckBox, QProgressBar, QMessageBox, QGridLayout
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtCore import QByteArray, Qt, QBasicTimer, QThread, QEventLoop, Signal
from PySide6.QtGui import QIcon, QTextDocument, QTextOption
import bus_api, routemap

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

class BusInfoThread(QThread):
    def __init__(self, parent):
        super(BusInfoThread, self).__init__(parent)
        
        self.widget = parent
        
    def run(self):
        self.widget.bus_info_list, error = bus_api.search_bus_info(self.widget.key, self.widget.search_input.text(), return_error = True)
        
        if len(self.widget.bus_info_list) < 1: 
            self.widget.status_label.setText("검색 결과가 없습니다.")
        else:
            self.widget.status_label.setText("{}건의 검색 결과가 있습니다.".format(len(self.widget.bus_info_list)))
        
        if error:
            self.widget.status_label.setText(str(error))
            
        self.widget.result_table.setRowCount(len(self.widget.bus_info_list))
        
        for i, bus in enumerate(self.widget.bus_info_list):
            item_region = QTableWidgetItem(bus_api.convert_type_to_region(bus['type']))
            item_type = QTableWidgetItem(bus_api.route_type_str[bus['type']])
            item_name = QTableWidgetItem(bus['name'])
            item_desc = QTableWidgetItem(bus['desc'])
            
            self.widget.result_table.setItem(i, 0, item_region)
            self.widget.result_table.setItem(i, 1, item_type)
            self.widget.result_table.setItem(i, 2, item_name)
            self.widget.result_table.setItem(i, 3, item_desc)
        
        self.widget.is_loading_bus_info = False
        self.widget.search_input.setEnabled(True)

class BusRouteThread(QThread):
    def __init__(self, parent, route_data):
        super(BusRouteThread, self).__init__(parent)
        
        self.widget = parent
        self.route_data = route_data
        
    def run(self):
        self.widget.preview_line_color, self.widget.preview_line_dark_color = routemap.get_bus_color(self.route_data)
        try:
            if self.route_data['type'] <= 10:
                route_positions = bus_api.get_seoul_bus_route(self.widget.key, self.route_data['id'])
                self.widget.route_info = bus_api.get_seoul_bus_type(self.widget.key, self.route_data['id'])
                self.widget.bus_stops = bus_api.get_seoul_bus_stops(self.widget.key, self.route_data['id'])
            elif self.route_data['type'] <= 60:
                route_positions = bus_api.get_gyeonggi_bus_route(self.widget.key, self.route_data['id'])
                self.widget.route_info = bus_api.get_gyeonggi_bus_type(self.widget.key, self.route_data['id'])
                self.widget.bus_stops = bus_api.get_gyeonggi_bus_stops(self.widget.key, self.route_data['id'])
            else:
                route_positions, route_bims_id = bus_api.get_busan_bus_route(self.route_data['name'])
                self.widget.route_info = bus_api.get_busan_bus_type(self.widget.key, route_bims_id)
                self.widget.bus_stops = bus_api.get_busan_bus_stops(self.widget.key, self.route_data['id'], route_bims_id)
            
            self.widget.preview_points = []

            for pos in route_positions:
                self.widget.preview_points.append(routemap.convert_pos(pos))
            
            self.widget.render_preview_routemap()
        except requests.exceptions.ConnectTimeout:
            self.widget.status_label.setText("[오류] Connection Timeout")
            self.widget.svg_widget.load(QByteArray())
        except Exception as e:
            self.widget.status_label.setText("[오류] " + str(e))
            self.widget.svg_widget.load(QByteArray())
        
        self.widget.is_loading_bus_route = False
        self.widget.result_table.setEnabled(True)
        self.widget.execute_button.setEnabled(True)
        
class OverwriteWindow(QWidget):
    result_signal = Signal(int)
    
    def __init__(self, parent, filename):
        super().__init__()
        
        self.setWindowTitle(" ")
        self.setWindowModality(Qt.ApplicationModal)
        
        icon = QIcon(resource_path("resources/icon.ico"))
        self.setWindowIcon(icon)
        
        self.text_label = QLabel('<p style="margin-bottom: 10px"><b>이름이 "{}"인 파일이 이미 존재합니다.</p><p>덮어쓰시겠습니까?</p>'.format(filename))
        
        self.text_label.setTextFormat(Qt.RichText)
        
        self.yes_button = QPushButton("덮어쓰기")
        self.no_button = QPushButton("취소")
        
        self.yes_button.clicked.connect(self.click_yes)
        self.no_button.clicked.connect(self.click_no)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.yes_button)
        button_layout.addWidget(self.no_button)
        
        layout = QVBoxLayout()
        layout.addWidget(self.text_label)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.setFixedSize(320, 100)
        
        self.destroyed.connect(self.cancel)
    
    def cancel(self):
        self.result_signal.emit(0)
    
    def click_yes(self):
        self.result_signal.emit(1)
        self.close()
    
    def click_no(self):
        self.result_signal.emit(0)
        self.close()

class RenderWindow(QWidget):
    def __init__(self, parent, route_info, bus_stops, points):
        super().__init__()
        
        self.parent_widget = parent
        
        self.route_info = route_info
        self.bus_stops = bus_stops
        self.points = points
        
        self.mapbox_key = parent.mapbox_key
        self.key = parent.key
        
        self.setWindowTitle("{}".format(route_info['name']))
        
        icon = QIcon(resource_path("resources/icon.ico"))
        self.setWindowIcon(icon)
        
        group_theme = QGroupBox("테마")
        self.button_light_theme = QRadioButton("밝은 테마", group_theme)
        self.button_dark_theme = QRadioButton("어두운 테마", group_theme)
        
        self.button_light_theme.setChecked(True)
        
        theme_button_layout = QHBoxLayout(group_theme)
        theme_button_layout.addWidget(self.button_light_theme)
        theme_button_layout.addWidget(self.button_dark_theme)
        
        group_oneway = QGroupBox("노선 형태")
        self.button_oneway_yes = QRadioButton("편방향", group_oneway)
        self.button_oneway_no = QRadioButton("양방향", group_oneway)
        
        if routemap.distance(points[0], points[-1]) > 50:
            self.button_oneway_yes.setChecked(True)
        else:
            self.button_oneway_no.setChecked(True)
        
        oneway_button_layout = QHBoxLayout(group_oneway)
        oneway_button_layout.addWidget(self.button_oneway_yes)
        oneway_button_layout.addWidget(self.button_oneway_no)
        
        group_etc = QGroupBox("기타")
        self.checkbox_background_map = QCheckBox("배경 지도 사용", group_etc)
        
        if not self.mapbox_key:
            self.checkbox_background_map.setEnabled(False)
            self.checkbox_background_map.setChecked(False)
        else:
            self.checkbox_background_map.setChecked(True)
        
        group_etc_layout = QVBoxLayout(group_etc)
        group_etc_layout.addWidget(self.checkbox_background_map)
        
        self.execute_button = QPushButton("저장")
        
        default_filename = '{}.svg'.format(self.route_info['name'])
        
        self.filename_input = QLineEdit()
        self.filename_input.setText(default_filename)
        
        execute_layout = QHBoxLayout()
        execute_layout.addWidget(self.filename_input, stretch = 1)
        execute_layout.addWidget(self.execute_button)

        layout = QVBoxLayout()
        layout.addWidget(group_theme)
        layout.addWidget(group_oneway)
        layout.addWidget(group_etc)
        layout.addStretch(1)
        layout.addLayout(execute_layout)

        self.setLayout(layout)
        self.setFixedSize(240, 240)
        
        self.execute_button.clicked.connect(self.render)
    
    def handle_result_status(self, value):
        self.overwrite_result = value
    
    def render(self):
        filename = self.filename_input.text()
        folder_path = os.path.dirname(filename)
        
        if folder_path != '' and not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        self.overwrite_result = 0
        
        if os.path.exists(filename):
            dialog = OverwriteWindow(self, filename)
            dialog.show()
            
            loop = QEventLoop()
            dialog.result_signal.connect(self.handle_result_status)
            dialog.result_signal.connect(loop.quit)
            
            loop.exec()
            
            if self.overwrite_result == 0:
                return
        
        theme = 'light' if self.button_light_theme.isChecked() else 'dark'
        is_one_way = self.button_oneway_yes.isChecked()
        draw_background_map = self.checkbox_background_map.isChecked()
    
        bus_routemap = routemap.RouteMap(self.route_info, self.bus_stops, self.points, is_one_way = is_one_way)
        
        route_size = bus_routemap.mapframe.size()
        
        if route_size[0] < route_size[1] / 1.5:
            route_size = (route_size[1] / 1.5, route_size[1])
        elif route_size[1] < route_size[0] / 1.5:
            route_size = (route_size[0], route_size[0] / 1.5)
        
        size_factor = route_size[0] / 640
        min_interval = 60 * size_factor
        
        svg = bus_routemap.render(size_factor, min_interval, theme)
        
        bus_routemap.mapframe.extend(size_factor * 30)
        
        if theme == 'light':
            mapbox_style = 'kiwitree/clinp1vgh002t01q4c2366q3o'
            page_color = '#ffffff'
        elif theme == 'dark':
            mapbox_style = 'kiwitree/clirdaqpr00hu01pu8t7vhmq7'
            page_color = '#282828'
        
        with open(filename, mode='w+', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
            f.write('<svg width="{0}" height="{1}" viewBox="0 0 {0} {1}" xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"><style></style>\n'.format(bus_routemap.mapframe.width(), bus_routemap.mapframe.height()))
            f.write('<sodipodi:namedview id="namedview1" pagecolor="{}" bordercolor="#cccccc" borderopacity="1" inkscape:deskcolor="#e5e5e5"/>'.format(page_color))
            f.write('<g transform="translate({}, {})">\n'.format(-bus_routemap.mapframe.left, -bus_routemap.mapframe.top))
            
            if draw_background_map:
                f.write(bus_api.get_mapbox_map(bus_routemap.mapframe, self.mapbox_key, mapbox_style))
            
            f.write(svg)
            f.write('</g>')
            f.write('</svg>')
        
        self.parent_widget.status_label.setText('"{}"로 내보냈습니다.'.format(filename))
        self.close()

class OptionsWindow(QWidget):
    def __init__(self, parent):
        super().__init__()
        
        self.parent_widget = parent
        
        self.mapbox_key = parent.mapbox_key
        self.key = parent.key
        
        self.setWindowTitle("설정")
        
        icon = QIcon(resource_path("resources/icon.ico"))
        self.setWindowIcon(icon)
        
        group_api_key = QGroupBox("API 키")
        
        self.openapi_key_input = QLineEdit()
        self.mapbox_key_input = QLineEdit()
        
        self.openapi_key_input.setText(self.key)
        self.mapbox_key_input.setText(self.mapbox_key)
        
        api_key_grid_layout = QGridLayout(group_api_key)
        
        api_key_grid_layout.addWidget(QLabel("OpenAPI 키: "), 0, 0)
        api_key_grid_layout.addWidget(self.openapi_key_input, 0, 1)
        api_key_grid_layout.addWidget(QLabel("Mapbox 키: "), 1, 0)
        api_key_grid_layout.addWidget(self.mapbox_key_input, 1, 1)
        
        self.cancel_button = QPushButton("취소")
        self.execute_button = QPushButton("저장")
        
        self.cancel_button.clicked.connect(self.cancel)
        self.execute_button.clicked.connect(self.save)
        
        execute_layout = QHBoxLayout()
        execute_layout.addStretch(1)
        execute_layout.addWidget(self.cancel_button)
        execute_layout.addWidget(self.execute_button)

        layout = QVBoxLayout()
        layout.addWidget(group_api_key)
        layout.addStretch(1)
        layout.addLayout(execute_layout)

        self.setLayout(layout)
        self.setFixedSize(360, 140)
    
    def cancel(self):
        self.close()
    
    def save(self):
        with open('key.json', mode='w', encoding='utf-8') as key_file:
            key_json = {'bus_api_key': self.openapi_key_input.text(), 'mapbox_key': self.mapbox_key_input.text()}
            json.dump(key_json, key_file, indent=4)
            
        self.parent_widget.key = self.openapi_key_input.text()
        self.parent_widget.mapbox_key = self.mapbox_key_input.text()
        
        self.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.load_key()
        self.bus_info_list = []
        self.preview_points = []
        
        self.is_loading_bus_info = False
        self.is_loading_bus_route = False
        
        self.setWindowTitle("버스 노선도 생성기 GUI")
        
        icon = QIcon(resource_path("resources/icon.ico"))
        self.setWindowIcon(icon)

        self.result_table = QTableWidget()
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["지역", "유형", "노선번호", "경유지"])
        self.result_table.setRowCount(0)
        self.result_table.itemClicked.connect(self.draw_route_preview)
        
        self.resize(800, 400)
        self.setMinimumSize(800, 400)
        
        self.result_table.setColumnWidth(0, 50)
        self.result_table.setColumnWidth(1, 50)
        self.result_table.setColumnWidth(2, 100)
        self.result_table.setColumnWidth(3, 220)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        self.svg_widget = QSvgWidget(self)
        
        self.search_input = QLineEdit()
        self.search_input.returnPressed.connect(self.search_input_return)
        
        search_label = QLabel("검색: ")
        
        self.status_label = QLabel()
        
        self.execute_button = QPushButton("생성")
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self.open_render_window)
        
        self.options_button = QPushButton("설정")
        self.options_button.clicked.connect(self.open_option_window)
        
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.status_label, stretch = 1)
        status_layout.addWidget(self.options_button)
        status_layout.addWidget(self.execute_button)
        
        search_layout = QHBoxLayout()
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        
        preview_label = QLabel("미리보기")
        
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(self.svg_widget, stretch = 1)
        
        viewer_layout = QHBoxLayout()
        viewer_layout.addWidget(self.result_table, stretch = 3)
        viewer_layout.addLayout(preview_layout, stretch = 2)
        
        layout = QVBoxLayout()
        layout.addLayout(search_layout)
        layout.addLayout(viewer_layout)
        layout.addLayout(status_layout)

        container = QWidget()
        container.setLayout(layout)

        self.setCentralWidget(container)
    
    def search_input_return(self):
        if not self.search_input.text():
            return
        
        if not self.is_loading_bus_info:
            self.is_loading_bus_info = True
            self.search_input.setEnabled(False)
            
            self.execute_button.setEnabled(False)
            self.result_table.clearSelection()
            self.svg_widget.load(QByteArray())
            
            bus_info_thread = BusInfoThread(self)
            bus_info_thread.run()
    
    def draw_route_preview(self, item):
        if not self.is_loading_bus_route:
            self.is_loading_bus_route = True
            self.result_table.setEnabled(False)
            
            route_data = self.bus_info_list[item.row()]
            
            bus_route_thread = BusRouteThread(self, route_data)
            bus_route_thread.run()
    
    def open_render_window(self):
        self.render_window = RenderWindow(self, self.route_info, self.bus_stops, self.preview_points)
        self.render_window.show()
    
    def open_option_window(self):
        self.option_window = OptionsWindow(self)
        self.option_window.show()
    
    def load_key(self):
        try:
            with open('key.json', mode='r', encoding='utf-8') as key_file:
                global key, naver_key_id, naver_key
                key_json = json.load(key_file)
                
                self.key = key_json['bus_api_key']
                self.mapbox_key = key_json['mapbox_key']
        except FileNotFoundError:
            with open('key.json', mode='w', encoding='utf-8') as key_file:
                key_json = {'bus_api_key': '', 'mapbox_key': ''}
                json.dump(key_json, key_file, indent=4)
            
            self.key = ''
            self.mapbox_key = ''
    
    def render_preview_routemap(self):
        if not self.preview_points:
            return
        
        min_x = min(x for x, _ in self.preview_points)
        max_x = max(x for x, _ in self.preview_points)
        min_y = min(y for _, y in self.preview_points)
        max_y = max(y for _, y in self.preview_points)
        
        draw_points = []
        
        width = 300
        height = 300
        
        if (max_x - min_x) / (max_y - min_y) > self.svg_widget.width() / self.svg_widget.height():
            height = width / self.svg_widget.width() * self.svg_widget.height()
            offset_x = 2
            offset_y = height / 2 - ((max_y - min_y) * (width - offset_x * 2) / (max_x - min_x) / 2)
            for x, y in self.preview_points:
                adjusted_x = offset_x + (x - min_x) * (width - offset_x * 2) / (max_x - min_x)
                adjusted_y = offset_y + (y - min_y) * (width - offset_x * 2) / (max_x - min_x)
                draw_points.append((adjusted_x, adjusted_y))
        else:
            width = height / self.svg_widget.height() * self.svg_widget.width()
            offset_y = 2
            offset_x = width / 2 - ((max_x - min_x) * (height - offset_y * 2) / (max_y - min_y) / 2)
            for x, y in self.preview_points:
                adjusted_x = offset_x + (x - min_x) * (height - offset_y * 2) / (max_y - min_y)
                adjusted_y = offset_y + (y - min_y) * (height - offset_y * 2) / (max_y - min_y)
                draw_points.append((adjusted_x, adjusted_y))
        
        style_path = "display:inline;fill:none;stroke:{};stroke-width:{};stroke-linecap:round;stroke-linejoin:round;stroke-miterlimit:4;stroke-dasharray:none;stroke-opacity:1".format(self.preview_line_color, 2)
        
        svg_path = routemap.make_svg_path(style_path, draw_points)
        
        svg_data = '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" width="{}" height="{}">'.format(width, height)
        svg_data += svg_path + '</svg>'
        
        self.svg_widget.load(QByteArray(svg_data.encode()))
    
    def resizeEvent(self, event):
        self.render_preview_routemap()
    
if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()