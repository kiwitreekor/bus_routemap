import os, sys, json, requests, threading, shutil
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QAbstractItemView, QPushButton, QGroupBox, QRadioButton, QSpacerItem, QCheckBox, QProgressBar, QMessageBox, QGridLayout, QSlider, QDialog
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtCore import QByteArray, Qt, QBasicTimer, QObject, QEventLoop, Signal, Slot, QThread
from PySide6.QtGui import QIcon, QTextDocument, QTextOption, QIntValidator
import bus_api, routemap, mapbox

version = '1.1'

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

class BusInfoThread(QObject):
    thread_finished = Signal(str)
    
    def __init__(self, parent):
        super(BusInfoThread, self).__init__(parent)
        self.widget = parent
        
    def run(self):
        bus_info_list, error = bus_api.search_bus_info(self.widget.key, self.widget.search_input.text(), return_error = True)
        error_str = None
        if error:
            error_str = str(error)
        result_json = json.dumps({'result': bus_info_list, 'error': error_str})
        
        self.thread_finished.emit(result_json)

class BusRouteThread(QObject):
    thread_finished = Signal(str)
    
    def __init__(self, parent):
        super(BusRouteThread, self).__init__(parent)
        
        self.widget = parent
        
    def run(self, route_data):
        error = None
        route_positions = None
        route_info = None
        bus_stops = None
        
        try:
            if route_data['type'] <= 10:
                route_positions = bus_api.get_seoul_bus_route(self.widget.key, route_data['id'])
                route_info = bus_api.get_seoul_bus_type(self.widget.key, route_data['id'])
                bus_stops = bus_api.get_seoul_bus_stops(self.widget.key, route_data['id'])
            elif route_data['type'] <= 60:
                route_positions = bus_api.get_gyeonggi_bus_route(self.widget.key, route_data['id'])
                route_info = bus_api.get_gyeonggi_bus_type(self.widget.key, route_data['id'])
                bus_stops = bus_api.get_gyeonggi_bus_stops(self.widget.key, route_data['id'])
            else:
                route_positions, route_bims_id = bus_api.get_busan_bus_route(route_data['name'])
                route_info = bus_api.get_busan_bus_type(self.widget.key, route_bims_id)
                bus_stops = bus_api.get_busan_bus_stops(self.widget.key, route_data['id'], route_bims_id)
        except requests.exceptions.ConnectTimeout:
            error = "[오류] Connection Timeout"
        except Exception as e:
            error = "[오류] " + str(e)
        
        result_json = json.dumps({'result': {'route_positions': route_positions, 'route_info': route_info, 'bus_stops': bus_stops}, 'error': error})
        self.thread_finished.emit(result_json)

class OkDialog(QDialog):
    def __init__(self, parent, title, text):
        super().__init__()
        
        self.result = 0

        self.setWindowTitle(title)
        self.setWindowModality(Qt.ApplicationModal)
        
        icon = QIcon(resource_path("resources/icon.ico"))
        self.setWindowIcon(icon)
        
        self.text_label = QLabel(text)
        
        self.text_label.setTextFormat(Qt.RichText)
        
        self.yes_button = QPushButton("확인")
        
        self.yes_button.clicked.connect(self.click_yes)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.yes_button)
        
        layout = QVBoxLayout()
        layout.addWidget(self.text_label)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.setFixedSize(320, 100)
    
    def exec(self):
        super().exec()
        return self.result
    
    def click_yes(self):
        self.result = 1
        self.close()

class OkCancelDialog(QDialog):
    def __init__(self, parent, title, text):
        super().__init__()
        
        self.result = 0
        
        self.setWindowTitle(title)
        self.setWindowModality(Qt.ApplicationModal)
        
        self.text_label = QLabel(text)
        
        self.text_label.setTextFormat(Qt.RichText)
        
        self.yes_button = QPushButton("확인")
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
    
    def exec(self):
        super().exec()
        return self.result
    
    def click_yes(self):
        self.result = 1
        self.close()
    
    def click_no(self):
        self.result = 0
        self.close()

class BusInfoEditWindow(QWidget):
    def __init__(self, parent):
        super().__init__()
        
        self.window = parent
        
        self.setWindowTitle(" ")
        
        icon = QIcon(resource_path("resources/icon.ico"))
        self.setWindowIcon(icon)
        
        self.setFixedSize(240, 120)
        
        bus_info_layout = QGridLayout()
        
        self.name_input = QLineEdit()
        self.start_input = QLineEdit()
        self.end_input = QLineEdit()
        
        self.name_input.setText(self.window.route_info['name'])
        self.start_input.setText(self.window.route_info['start'])
        self.end_input.setText(self.window.route_info['end'])
        
        self.name_input.returnPressed.connect(self.ok)
        self.start_input.returnPressed.connect(self.ok)
        self.end_input.returnPressed.connect(self.ok)
        
        bus_info_layout.addWidget(QLabel("노선명: "), 0, 0)
        bus_info_layout.addWidget(self.name_input, 0, 1)
        
        bus_info_layout.addWidget(QLabel("기점: "), 1, 0)
        bus_info_layout.addWidget(self.start_input, 1, 1)
        bus_info_layout.addWidget(QLabel("종점: "), 2, 0)
        bus_info_layout.addWidget(self.end_input, 2, 1)
        
        self.button_ok = QPushButton("확인")
        self.button_ok.clicked.connect(self.ok)
        
        apply_layout = QHBoxLayout()
        apply_layout.addStretch(1)
        apply_layout.addWidget(self.button_ok)
        
        layout = QVBoxLayout()
        layout.addLayout(bus_info_layout)
        layout.addStretch(1)
        layout.addLayout(apply_layout)
        
        self.setLayout(layout)
    
    def ok(self):
        self.window.route_info['name'] = self.name_input.text()
        self.window.route_info['start'] = self.start_input.text()
        self.window.route_info['end'] = self.end_input.text()
        
        self.window.refresh_preview()
        self.close()

class BusStopEditWindow(QWidget):
    def __init__(self, parent):
        super().__init__()
        
        self.window = parent
        
        self.setWindowTitle("정류장 목록 편집")
        
        icon = QIcon(resource_path("resources/icon.ico"))
        self.setWindowIcon(icon)
        
        self.setFixedSize(640, 400)

        self.bus_stop_table = QTableWidget()
        self.bus_stop_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.bus_stop_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.bus_stop_table.setColumnCount(7)
        self.bus_stop_table.setHorizontalHeaderLabels(["ID", "이름", "표시명", "구간", "경유", "위치", ""])
        self.bus_stop_table.setRowCount(0)
        # self.bus_stop_table.itemClicked.connect(self.draw_route_preview)
        
        self.bus_stop_table.setColumnWidth(0, 45)
        self.bus_stop_table.setColumnWidth(1, 200)
        self.bus_stop_table.setColumnWidth(2, 150)
        self.bus_stop_table.setColumnWidth(3, 45)
        self.bus_stop_table.setColumnWidth(4, 45)
        self.bus_stop_table.setColumnWidth(5, 45)
        self.bus_stop_table.setColumnWidth(6, 20)
        
        self.checkbox_list = []
        
        for i in range(len(parent.bus_stops)):
            checkbox = QCheckBox()
            self.checkbox_list.append(checkbox)
            
        self.load_table()
        self.bus_stop_table.itemChanged.connect(self.validate_table)
        
        self.button_apply = QPushButton("적용")
        self.button_apply.clicked.connect(self.apply)
        
        self.button_ok = QPushButton("확인")
        self.button_ok.clicked.connect(self.ok)
        
        apply_layout = QHBoxLayout()
        apply_layout.addStretch(1)
        apply_layout.addWidget(self.button_apply)
        apply_layout.addWidget(self.button_ok)
        
        layout = QVBoxLayout()
        layout.addWidget(self.bus_stop_table)
        layout.addLayout(apply_layout)
        
        self.setLayout(layout)
    
    def load_table(self):
        trans_id = self.window.trans_id
        self.bus_stop_table.setRowCount(len(self.window.bus_stops))
        
        for i, stop in enumerate(self.window.bus_stops):
            item_arsid = QTableWidgetItem(stop['arsid'])
            item_name = QTableWidgetItem(stop['name'])
            item_displayname = QTableWidgetItem('')
            item_section = QTableWidgetItem('1' if i > trans_id else '0')
            
            pass_stop = bool(routemap.rx_pass_stop.search(stop['name']))
            item_pass = QTableWidgetItem('경유' if pass_stop else '정차')
            
            item_text_direction = QTableWidgetItem('-1')
            
            item_arsid.setFlags(item_section.flags() & ~Qt.ItemIsEditable)
            item_name.setFlags(item_section.flags() & ~Qt.ItemIsEditable)
            item_pass.setFlags(item_section.flags() & ~Qt.ItemIsEditable)
            
            self.bus_stop_table.setItem(i, 0, item_arsid)
            self.bus_stop_table.setItem(i, 1, item_name)
            self.bus_stop_table.setItem(i, 2, item_displayname)
            self.bus_stop_table.setItem(i, 3, item_section)
            self.bus_stop_table.setItem(i, 4, item_pass)
            self.bus_stop_table.setItem(i, 5, item_text_direction)
            
        for i in range(len(self.window.bus_stops)):
            cell_widget = QWidget()
            layout_checkbox = QHBoxLayout(cell_widget)
            layout_checkbox.addWidget(self.checkbox_list[i])
            layout_checkbox.setAlignment(Qt.AlignCenter)
            layout_checkbox.setContentsMargins(0, 0, 0, 0)
            cell_widget.setLayout(layout_checkbox)
            
            self.bus_stop_table.setCellWidget(i, 6, cell_widget)
        
        for stop in self.window.render_bus_stop_list:
            self.checkbox_list[stop['ord']].setChecked(True)
            section = str(stop['section'])
            
            self.bus_stop_table.item(stop['ord'], 2).setText(stop['name'])
            self.bus_stop_table.item(stop['ord'], 3).setText(section)
            
            if 'text_dir' in stop:
                self.bus_stop_table.item(stop['ord'], 5).setText(str(stop['text_dir']))
            
        self.initial_sections = [self.bus_stop_table.item(i, 3).text() for i in range(len(self.window.bus_stops))]
    
    def validate_table(self, item):
        if item.column() == 3:
            if item.text() != '0' and item.text() != '1':
                item.setText(self.initial_sections[item.row()])
        elif item.column() == 5:
            try:
                int(item.text())
            except ValueError:
                item.setText('-1')
    
    def apply(self):
        bus_stop_list = []
        new_trans_id = 0
        
        for i in range(len(self.window.bus_stops)):
            try:
                section = int(self.bus_stop_table.item(i, 3).text())
            except ValueError:
                section = 0 if new_trans_id == 0 else 1
            
            if self.checkbox_list[i].isChecked():
                name = self.bus_stop_table.item(i, 1).text()
                display_name = self.bus_stop_table.item(i, 2).text()
                pass_stop = bool(self.bus_stop_table.item(i, 4).text() == '경유')
                try:
                    text_dir = int(self.bus_stop_table.item(i, 5).text())
                except ValueError:
                    text_dir = -1
                
                if display_name:
                    name = display_name
                
                pos = routemap.convert_pos(self.window.bus_stops[i]['pos'])
                bus_stop_list.append({'ord': i, 'pos': pos, 'name': name, 'section': section, 'pass': pass_stop, 'text_dir': text_dir})
            
            if section == 1 and new_trans_id == 0:
                new_trans_id = i - 1
        
        self.window.render_bus_stop_list = bus_stop_list
        self.window.trans_id = new_trans_id
        
        self.load_table()
        self.window.refresh_preview()
    
    def ok(self):
        self.apply()
        self.close()

class SizeSlider(QWidget):
    valueChanged = Signal()
    
    def __init__(self):
        super().__init__()
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(50, 200)
        self.slider.setValue(100)
        self.slider.valueChanged.connect(self.update_label)
        self.slider.sliderReleased.connect(self.emit_value_changed)
        
        self.label = QLabel(str(self.slider.value()) + '%')
        self.label.setFixedWidth(40)
        
        layout = QHBoxLayout()
        layout.addWidget(self.slider, stretch = 1)
        layout.addWidget(self.label)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.setLayout(layout)
    
    def value(self):
        return self.slider.value()
    
    def update_label(self):
        self.label.setText(str(self.slider.value()) + '%')
    
    def emit_value_changed(self):
        self.valueChanged.emit()

class RenderThread(QThread):
    render_finished = Signal()

    def __init__(self, parent, draw_background_map = False):
        super().__init__(parent=parent)
        self.draw_background_map = draw_background_map

    def run(self):
        parent = self.parent()
        theme = 'light' if parent.button_light_theme.isChecked() else 'dark'
        is_one_way = parent.button_oneway_yes.isChecked()
    
        parent.bus_routemap = routemap.RouteMap(parent.route_info, parent.bus_stops, parent.points, is_one_way = is_one_way, theme = theme)
        
        route_size = parent.bus_routemap.mapframe.size()
        
        if route_size[0] < route_size[1] / 1.5:
            route_size = (route_size[1] / 1.5, route_size[1])
        elif route_size[1] < route_size[0] / 1.5:
            route_size = (route_size[0], route_size[0] / 1.5)
        
        size_factor_base = route_size[0] / 640
        route_size_factor = size_factor_base * (parent.size_slider.value() / 100)
        info_size_factor = size_factor_base * (parent.info_size_slider.value() / 100) * 0.75
        circle_size_factor = size_factor_base * (parent.circle_size_slider.value() / 100)
        text_size_factor = size_factor_base * (parent.text_size_slider.value() / 100)
        min_interval = 60 * route_size_factor
        
        if parent.render_bus_stop_list == None:
            parent.render_bus_stop_list = parent.bus_routemap.parse_bus_stops(min_interval)
            parent.trans_id = parent.bus_routemap.trans_id
        else:
            parent.bus_routemap.update_trans_id(parent.trans_id)
        
        # 노선도 렌더링
        parent.bus_routemap.render_init()
        
        parent.svg_map = parent.bus_routemap.render_path(route_size_factor)
        for stop in parent.render_bus_stop_list:
            parent.svg_map += parent.bus_routemap.draw_bus_stop_circle(stop, circle_size_factor)
            
            if 'text_dir' in stop:
                parent.svg_map += parent.bus_routemap.draw_bus_stop_text(stop, text_size_factor, stop['text_dir'])
            else:
                parent.svg_map += parent.bus_routemap.draw_bus_stop_text(stop, text_size_factor)
        parent.svg_map += parent.bus_routemap.draw_bus_info(info_size_factor) + '\n'
        
        parent.bus_routemap.mapframe.extend(size_factor_base * 30)
        
        if theme == 'light':
            mapbox_style = 'kiwitree/clinp1vgh002t01q4c2366q3o'
            page_color = '#ffffff'
        elif theme == 'dark':
            mapbox_style = 'kiwitree/clirdaqpr00hu01pu8t7vhmq7'
            page_color = '#282828'
        
        if self.draw_background_map:
            try:
                parent.svg_map = bus_api.get_mapbox_map(parent.bus_routemap.mapframe, parent.mapbox_key, mapbox_style) + parent.svg_map
            except Exception as e:
                self.render_error.emit(type(e).__name__ + ": " + str(e))
                raise
        else:
            x = parent.bus_routemap.mapframe.left
            y = parent.bus_routemap.mapframe.top
            width = parent.bus_routemap.mapframe.width()
            height = parent.bus_routemap.mapframe.height()
            
            parent.svg_map = '<rect x="{}" y="{}" width="{}" height="{}" style="fill:{}" />'.format(x, y, width, height, page_color) + parent.svg_map
        
        self.render_finished.emit()

class RenderWindow(QWidget):
    render_error = Signal(str)
    
    def __init__(self, parent, route_info, bus_stops, points):
        super().__init__()
        
        self.parent_widget = parent
        
        self.route_info = route_info
        self.bus_stops = bus_stops
        self.points = points
        
        self.mapbox_key = parent.mapbox_key
        self.key = parent.key
        
        self.svg_map = None
        self.render_bus_stop_list = None
        
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
        
        group_route_edit = QGroupBox("노선 형태")
        self.button_oneway_yes = QRadioButton("편방향", group_route_edit)
        self.button_oneway_no = QRadioButton("양방향", group_route_edit)
        
        if routemap.distance(points[0], points[-1]) > 50:
            self.button_oneway_yes.setChecked(True)
        else:
            self.button_oneway_no.setChecked(True)
        
        oneway_button_layout = QHBoxLayout()
        oneway_button_layout.addWidget(self.button_oneway_yes)
        oneway_button_layout.addWidget(self.button_oneway_no)
        
        self.button_edit_stops = QPushButton("정류장 목록 편집")
        self.button_edit_stops.clicked.connect(self.bus_stop_edit_window)
        
        self.button_edit_info = QPushButton("버스 정보 편집")
        self.button_edit_info.clicked.connect(self.bus_info_edit_window)
        
        route_edit_layout = QVBoxLayout(group_route_edit)
        route_edit_layout.addLayout(oneway_button_layout)
        route_edit_layout.addWidget(self.button_edit_stops)
        route_edit_layout.addWidget(self.button_edit_info)
        
        group_size_slider = QGroupBox("크기")
        slider_layout = QGridLayout(group_size_slider)
        
        self.size_slider = SizeSlider()
        self.circle_size_slider = SizeSlider()
        self.text_size_slider = SizeSlider()
        self.info_size_slider = SizeSlider()
        
        self.size_slider.valueChanged.connect(self.refresh_preview)
        self.circle_size_slider.valueChanged.connect(self.refresh_preview)
        self.text_size_slider.valueChanged.connect(self.refresh_preview)
        self.info_size_slider.valueChanged.connect(self.refresh_preview)
        
        slider_layout.addWidget(QLabel("경로: "), 0, 0)
        slider_layout.addWidget(QLabel("정류장: "), 1, 0)
        slider_layout.addWidget(QLabel("정류장명: "), 2, 0)
        slider_layout.addWidget(QLabel("정보: "), 3, 0)
        
        slider_layout.addWidget(self.size_slider, 0, 1)
        slider_layout.addWidget(self.circle_size_slider, 1, 1)
        slider_layout.addWidget(self.text_size_slider, 2, 1)
        slider_layout.addWidget(self.info_size_slider, 3, 1)
        
        group_etc = QGroupBox("기타")
        self.checkbox_background_map = QCheckBox("배경 지도 사용", group_etc)
        
        if not self.parent_widget.mapbox_key_valid:
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

        self.settings_layout = QVBoxLayout()
        self.settings_layout.addWidget(group_theme)
        self.settings_layout.addWidget(group_route_edit)
        self.settings_layout.addWidget(group_size_slider)
        self.settings_layout.addWidget(group_etc)
        self.settings_layout.addStretch(1)
        self.settings_layout.addLayout(execute_layout)
        
        preview_label = QLabel("미리보기")
        
        self.svg_container = QWidget()
        
        self.svg_widget = QSvgWidget(self.svg_container)
        self.svg_widget.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
        
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(self.svg_container, stretch = 1)
        
        layout = QHBoxLayout()
        layout.addLayout(preview_layout, stretch = 1)
        layout.addLayout(self.settings_layout)
        
        self.setLayout(layout)
        
        self.minimum_width = 720
        self.minimum_height = 440
        self.setFixedSize(self.minimum_width, self.minimum_height)
        
        self.execute_button.clicked.connect(self.export)
        
        self.button_light_theme.clicked.connect(self.refresh_preview)
        self.button_dark_theme.clicked.connect(self.refresh_preview)
        
        self.button_oneway_yes.clicked.connect(self.refresh_preview)
        self.button_oneway_no.clicked.connect(self.refresh_preview)
        
        self.checkbox_background_map.clicked.connect(self.refresh_preview)
    
    def showEvent(self, event):
        self.refresh_preview()
    
    def bus_stop_edit_window(self):
        self.stop_edit_window = BusStopEditWindow(self)
        self.stop_edit_window.show()
    
    def bus_info_edit_window(self):
        self.info_edit_window = BusInfoEditWindow(self)
        self.info_edit_window.show()
    
    def refresh_preview(self):
        self.render_thread = RenderThread(self, self.checkbox_background_map.isChecked())
        self.render_thread.start()
        self.render_thread.render_finished.connect(self.refresh_preview_after)
        QApplication.setOverrideCursor(Qt.WaitCursor)

    def refresh_preview_after(self):
        width = self.bus_routemap.mapframe.width()
        height = self.bus_routemap.mapframe.height()
        
        svg = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        svg += '<svg width="{0}" height="{1}" viewBox="0 0 {0} {1}" xmlns="http://www.w3.org/2000/svg"><style></style>\n'.format(width, height)
        svg += '<g transform="translate({}, {})">\n'.format(-self.bus_routemap.mapframe.left, -self.bus_routemap.mapframe.top)
        svg += self.svg_map
        svg += '</g></svg>'
        
        if height > width:
            widget_width = self.svg_container.width()
            widget_height = self.svg_container.width() / width * height
        else:
            widget_width = self.svg_container.height() * width / height
            widget_height = self.svg_container.height()
        
        self.svg_widget.load(QByteArray(svg.encode()))
        self.svg_widget.resize(widget_width, widget_height)
        
        window_width = self.width()
        window_height = self.height()
        
        if width > height:
            self.setFixedSize(max(self.minimum_width, window_width + (widget_width - self.svg_container.width())), window_height)
        else:
            self.setFixedSize(window_width, max(self.minimum_height, window_height + (widget_height - self.svg_container.height())))
            
        QApplication.restoreOverrideCursor()
        QApplication.processEvents()
    
    def export(self):
        filename = self.filename_input.text()
        folder_path = os.path.dirname(filename)
        
        if folder_path != '' and not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        self.overwrite_result = 0
        
        if os.path.exists(filename):
            dialog = OkCancelDialog(self, ' ', '<p style="margin-bottom: 10px"><b>이름이 "{}"인 파일이 이미 존재합니다.</p><p>덮어쓰시겠습니까?</p>'.format(filename))
            result = dialog.exec()
            
            if not result:
                return
        
        width = self.bus_routemap.mapframe.width()
        height = self.bus_routemap.mapframe.height()
        
        if self.button_light_theme.isChecked():
            page_color = '#ffffff'
        else:
            page_color = '#282828'
        
        with open(filename, mode='w+', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
            f.write('<svg width="{0}" height="{1}" viewBox="0 0 {0} {1}" xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"><style></style>\n'.format(width, height))
            f.write('<sodipodi:namedview id="namedview1" pagecolor="{}" bordercolor="#cccccc" borderopacity="1" inkscape:deskcolor="#e5e5e5"/>'.format(page_color))
            f.write('<g transform="translate({}, {})">\n'.format(-self.bus_routemap.mapframe.left, -self.bus_routemap.mapframe.top))
            f.write(self.svg_map)
            f.write('</g></svg>')
        
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
        self.parent_widget.update_key(self.openapi_key_input.text(), self.mapbox_key_input.text())
        self.parent_widget.save_key()
        self.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.load_key()
        self.bus_info_list = []
        self.preview_points = []
            
        self.bus_info_thread = BusInfoThread(self)
        self.bus_route_thread = BusRouteThread(self)
        
        self.bus_info_thread.thread_finished.connect(self.bus_info_finished)
        self.bus_route_thread.thread_finished.connect(self.bus_route_finished)
        
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
        self.svg_widget = QSvgWidget(self)
        
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
    
    def showEvent(self, event):
        self.check_key_valid()
    
    def closeEvent(self, event):
        self.save_key()
        super().closeEvent(event)
        
    def update_key(self, key, mapbox_key):
        self.key = key
        self.mapbox_key = mapbox_key
        
        self.seoul_key_valid = bus_api.check_seoul_key_valid(self.key)
        self.gyeonggi_key_valid = bus_api.check_gyeonggi_key_valid(self.key)
        self.busan_key_valid = bus_api.check_busan_key_valid(self.key)
        self.mapbox_key_valid = mapbox.check_token_valid(self.mapbox_key)
    
    def check_key_valid(self):
        if not self.seoul_key_valid and not self.gyeonggi_key_valid and not self.busan_key_valid:
            self.key_error_dialog = OkDialog(self, '오류', 
                '<p><b>OpenAPI 키가 올바르지 않습니다.</b></p>' +
                '<p>서울시, 경기도, 부산시 버스정보시스템 API 키를 아래 사이트에서<br/>각각 발급받아야 사용할 수 있습니다.'+
                '<ul><li>서울시 API: <a href="https://www.data.go.kr/data/15000193/openapi.do">https://www.data.go.kr/data/15000193/openapi.do</a></li>' +
                '<li>경기도 API: <a href="https://www.data.go.kr/data/15080662/openapi.do">https://www.data.go.kr/data/15080662/openapi.do</a></li>' +
                '<li>부산시 API: <a href="https://www.data.go.kr/data/15092750/openapi.do">https://www.data.go.kr/data/15092750/openapi.do</a></li></ul></p>')
            self.key_error_dialog.setFixedSize(450, 180)
            self.key_error_dialog.show()
            
            loop = QEventLoop()
            self.key_error_dialog.result_signal.connect(loop.quit)
            
            loop.exec()
        
        if not self.mapbox_key_valid:
            self.mapbox_key_error_dialog = OkDialog(self, '오류', '<p style="margin-bottom:5px"><b>Mapbox 키가 올바르지 않습니다.</b></p><p>배경 지도를 사용하려면 Mapbox 키가 유효해야 합니다.</p>')
            self.mapbox_key_error_dialog.setFixedSize(360, 100)
            self.mapbox_key_error_dialog.show()
            
            loop = QEventLoop()
            self.mapbox_key_error_dialog.result_signal.connect(loop.quit)
            
            loop.exec()
    
    def search_input_return(self):
        if not self.search_input.text():
            return
        
        self.search_input.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.result_table.clearSelection()
        self.svg_widget.load(QByteArray())
        
        t = threading.Thread(target=self.bus_info_thread.run)
        t.daemon = True
        t.start()
    
    @Slot(str)
    def bus_info_finished(self, result_json):
        result = json.loads(result_json)
        
        self.bus_info_list = result['result']
        
        if len(self.bus_info_list) < 1: 
            self.status_label.setText("검색 결과가 없습니다.")
        else:
            self.status_label.setText("{}건의 검색 결과가 있습니다.".format(len(self.bus_info_list)))
        
        if result['error'] != None:
            self.status_label.setText(result['error'])
            
        self.result_table.setRowCount(len(self.bus_info_list))
        
        for i, bus in enumerate(self.bus_info_list):
            item_region = QTableWidgetItem(bus_api.convert_type_to_region(bus['type']))
            item_type = QTableWidgetItem(bus_api.route_type_str[bus['type']])
            item_name = QTableWidgetItem(bus['name'])
            item_desc = QTableWidgetItem(bus['desc'])
            
            self.result_table.setItem(i, 0, item_region)
            self.result_table.setItem(i, 1, item_type)
            self.result_table.setItem(i, 2, item_name)
            self.result_table.setItem(i, 3, item_desc)
            
        self.search_input.setEnabled(True)
    
    def draw_route_preview(self, item):
        self.result_table.setEnabled(False)
        route_data = self.bus_info_list[item.row()]
        
        self.preview_line_color, self.preview_line_dark_color = routemap.get_bus_color(route_data)
        
        t = threading.Thread(target=self.bus_route_thread.run, args=(route_data,))
        t.daemon = True
        t.start()
    
    @Slot(str)
    def bus_route_finished(self, result_json):
        result = json.loads(result_json)
        
        self.result_table.setEnabled(True)
        self.execute_button.setEnabled(True)
        
        if result['error'] != None:
            self.status_label.setText(result['error'])
            self.svg_widget.load(QByteArray())
            return
        
        self.route_info = result['result']['route_info']
        self.bus_stops = result['result']['bus_stops']
        route_positions = result['result']['route_positions']
        
        self.preview_points = []

        for pos in route_positions:
            self.preview_points.append(routemap.convert_pos(pos))
        
        self.render_preview_routemap()
    
    def open_render_window(self):
        self.render_window = RenderWindow(self, self.route_info, self.bus_stops, self.preview_points)
        self.render_window.render_error.connect(self.render_error)
        self.render_window.show()
    
    def render_error(self, msg):
        self.status_label.setText("[오류] " + msg)
        del self.render_window
    
    def open_option_window(self):
        self.option_window = OptionsWindow(self)
        self.option_window.show()
    
    def load_key(self):
        try:
            with open('key.json', mode='r', encoding='utf-8') as key_file:
                key_json = json.load(key_file)
                self.update_key(key_json['bus_api_key'], key_json['mapbox_key'])

                # v1.1: cache structure changed
                if 'version' not in key_json:
                    shutil.rmtree(bus_api.cache_dir)
        except FileNotFoundError:
            with open('key.json', mode='w', encoding='utf-8') as key_file:
                key_json = {'bus_api_key': '', 'mapbox_key': '', 'version': version}
                json.dump(key_json, key_file, indent=4)
            
            self.key = ''
            self.mapbox_key = ''
    
    def save_key(self):
        with open('key.json', mode='w', encoding='utf-8') as key_file:
            key_json = {'bus_api_key': self.key, 'mapbox_key': self.mapbox_key, 'version': version}
            json.dump(key_json, key_file, indent=4)

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
    app.setStyleSheet("""
        QLineEdit { padding: 3px; border: 1px solid rgba(0, 0, 0, 10%); background-color: #fff; border-radius: 4px }
        QPushButton { padding: 4px; border: 1px solid rgba(0, 0, 0, 10%); background-color: #fff; border-radius: 4px; min-width: 75px; outline: 0px }
        QPushButton:hover { background-color: #f3f3f3; }
        QPushButton:pressed { background-color: #eee; }
        QPushButton:checked { background-color: #eee; }
        QTableWidget { border: 1px solid rgba(0, 0, 0, 10%); outline: 0px }
        QMenu { background-color: #fff; border: 1px solid rgba(0, 0, 0, 10%); border-radius: 6px; }
        QMenu::item { background-color: transparent; margin: 3px; padding: 4px 15px }
        QMenu::item:hover { background-color: #eee; color: #000; border-radius: 4px }
        QMenu::item:selected { background-color: #eee; color: #000; border-radius: 4px }
        QMenu::separator { border-top: 1px solid #ddd; height: 0px; }
    
        QScrollBar:vertical {
            background: #e0e0e0; /* 전체 배경 */
            width: 6px;
            margin: 0px 0px 0px 0px;
            border: none;
        }
        QScrollBar::handle:vertical {
            background: #c0c0c0; /* 핸들(스크롤 이동 부분) 색상 */
            min-height: 20px;
            border-radius: 3px;
        }
        QScrollBar::handle:vertical:hover {
            background: #a0a0a0; /* 핸들 호버 상태 색상 */
        }
        QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
            background: none;
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: #e0e0e0; /* 빈 공간 색상 */
        }
    
        QScrollBar:horizontal {
            background: #e0e0e0; /* 전체 배경 */
            height: 6px;
            margin: 0px 0px 0px 0px;
            border: none;
        }
        QScrollBar::handle:horizontal {
            background: #c0c0c0; /* 핸들(스크롤 이동 부분) 색상 */
            min-width: 20px;
            border-radius: 3px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #a0a0a0; /* 핸들 호버 상태 색상 */
        }
        QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal {
            background: none;
            width: 0px;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: #e0e0e0; /* 빈 공간 색상 */
        }
    """)

    window = MainWindow()
    window.show()

    app.exec()