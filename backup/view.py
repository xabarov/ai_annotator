from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QPolygonF, QColor, QPen
from PyQt5.QtWidgets import QAction, QMenu
from PyQt5.QtWidgets import QApplication

from utils import config
from utils import help_functions as hf

from ui.signals_and_slots import PolygonDeleteConnection, PolygonPressedConnection, PolygonEndDrawing, MaskEndDrawing, \
    PolygonChangeClsNumConnection, LoadIdProgress
from ui.polygons import GrPolygonLabel, GrEllipsLabel

import numpy as np
from shapely import Polygon, Point

from utils.ids_worker import IdsSetterWorker


class GraphicsView(QtWidgets.QGraphicsView):
    """
    Сцена для отображения текущей картинки и полигонов
    """

    def __init__(self, parent=None, active_color=None, fat_point_color=None, on_rubber_band_mode=None):
        """
        active_color - цвет активного полигона, по умолчанию config.ACTIVE_COLOR
        fat_point_color - цвет узлов активного полигона, по умолчанию config.FAT_POINT_COLOR
        """

        super().__init__(parent)
        scene = QtWidgets.QGraphicsScene(self)

        # SIGNALS
        self.polygon_clicked = PolygonPressedConnection()
        self.polygon_delete = PolygonDeleteConnection()
        self.polygon_cls_num_change = PolygonChangeClsNumConnection()
        self.load_ids_conn = LoadIdProgress()

        self.setScene(scene)

        self._pixmap_item = QtWidgets.QGraphicsPixmapItem()
        scene.addItem(self._pixmap_item)

        on_rubber_band_mode.connect(self.on_rb_mode_change)
        self.is_rubber_mode = False

        self.is_drawing = False
        self.drawing_type = "Polygon"
        self.active_item = None
        self.labels_ids = []

        if not active_color:
            self.active_color = config.ACTIVE_COLOR
        else:
            self.active_color = active_color

        if not fat_point_color:
            self.fat_point_color = config.FAT_POINT_COLOR
        else:
            self.fat_point_color = fat_point_color

        self.active_brush = QtGui.QBrush(QColor(*self.active_color), QtCore.Qt.SolidPattern)
        self.fat_point_brush = QtGui.QBrush(QColor(*self.fat_point_color), QtCore.Qt.SolidPattern)
        self.positive_point_brush = QtGui.QBrush(QColor(*config.POSITIVE_POINT_COLOR), QtCore.Qt.SolidPattern)
        self.negative_point_brush = QtGui.QBrush(QColor(*config.NEGATIVE_POINT_COLOR), QtCore.Qt.SolidPattern)

        self.setMouseTracking(False)
        self.fat_point = None
        self.drag_mode = "No"
        self.dragged_vertex = None
        self.ellips_start_point = None
        self.box_start_point = None

        self.polygon_end_drawing = PolygonEndDrawing()
        self.mask_end_drawing = MaskEndDrawing()
        self.min_ellips_size = 10
        self._zoom = 0
        self.fat_width_default_percent = 50

        self.negative_points = []
        self.positive_points = []
        self.right_clicked_points = []
        self.left_clicked_points = []
        self.buffer = None
        self.pressed_polygon = None
        self.create_actions()

    def create_actions(self):
        self.delPolyAct = QAction("Удалить полигон", self, enabled=True, triggered=self.del_polygon)
        self.changeClsNumAct = QAction("Изменить имя метки", self, enabled=True, triggered=self.change_cls_num)

    def change_cls_num(self):
        if self.pressed_polygon:
            change_id = self.pressed_polygon.id
            cls_num = self.pressed_polygon.cls_num
            self.polygon_cls_num_change.pol_cls_num_and_id.emit(cls_num, change_id)

    def del_polygon(self):
        if self.pressed_polygon:
            deleted_id = self.pressed_polygon.id
            self.remove_item(self.pressed_polygon, is_delete_id=True)
            self.pressed_polygon = None
            self.polygon_delete.id_delete.emit(deleted_id)

    @property
    def pixmap_item(self):
        return self._pixmap_item

    def setPixmap(self, pixmap):
        """
        Задать новую картинку
        """
        scene = QtWidgets.QGraphicsScene(self)
        self.setScene(scene)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem()
        scene.addItem(self._pixmap_item)
        self.pixmap_item.setPixmap(pixmap)
        self.set_fat_width()

    def clearScene(self):
        """
        Очистить сцену
        """
        scene = QtWidgets.QGraphicsScene(self)
        self.setScene(scene)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem()
        scene.addItem(self._pixmap_item)

    def activate_item_by_id(self, id_to_found):
        found_item = None
        for item in self.scene().items():
            # ищем плигон с заданным id
            try:
                if item.id == id_to_found:
                    found_item = item
                    break
            except:
                pass

        if found_item:
            found_item.setBrush(self.active_brush)
            found_item.setPen(self.active_pen)
            self.active_item = found_item
            self.switch_all_polygons_to_default_except_active()

        self.setFocus()

    def set_fat_width(self, fat_width_percent_new=None):
        """
        Определение и установка толщины граней активного полигона и эллипса узловой точки активного полигона
        """
        pixmap_width = self.pixmap_item.pixmap().width()
        scale = pixmap_width / 2000.0

        if fat_width_percent_new:
            fat_scale = 0.3 + fat_width_percent_new / 50.0
            self.fat_width_default_percent = fat_width_percent_new
        else:
            fat_scale = 0.3 + self.fat_width_default_percent / 50.0

        self.fat_width = fat_scale * scale * 12 + 1

        self.fat_area = config.FAT_AREA_AROUND
        self.line_width = int(self.fat_width / 8) + 1
        self.min_distance_to_lines = 3

        self.active_pen = QPen(QColor(*hf.set_alpha_to_max(self.active_color)), self.line_width, QtCore.Qt.SolidLine)
        self.fat_point_pen = QPen(QColor(*self.fat_point_color), self.line_width, QtCore.Qt.SolidLine)
        self.positive_point_pen = QPen(QColor(*config.POSITIVE_POINT_COLOR), self.line_width, QtCore.Qt.SolidLine)
        self.negative_point_pen = QPen(QColor(*config.NEGATIVE_POINT_COLOR), self.line_width, QtCore.Qt.SolidLine)

        self.min_ellips_size = self.fat_width
        self._zoom = 0

        return self.fat_width

    def toggle(self, item):
        if item.brush().color().getRgb() == self.active_brush.color().getRgb():
                item.setBrush(QtGui.QBrush(QColor(*item.color), QtCore.Qt.SolidPattern))
                item.setPen(QPen(QColor(*hf.set_alpha_to_max(item.color)), self.line_width, QtCore.Qt.SolidLine))
        else:
            item.setBrush(self.active_brush)
            item.setPen(self.active_pen)

    def is_close_to_fat_point(self, lp):
        """
        fat_point - Эллипс - узел полигона
        """
        if self.fat_point:
            scale = self._zoom / 3.0 + 1
            rect = self.fat_point.rect()
            width = abs(rect.topRight().x() - rect.topLeft().x())
            height = abs(rect.topRight().y() - rect.bottomRight().y())
            center = QtCore.QPointF(rect.topLeft().x() + width / 2, rect.topLeft().y() + height / 2)
            d = hf.distance(lp, center)
            if d < (self.fat_width / scale):
                return True

        return False

    def check_near_by_active_pressed(self, lp):
        scale = self._zoom / 3.0 + 1
        if self.active_item:
            try:
                pol = self.active_item.polygon()
                # shapely_pol = Polygon([(p.x(), p.y()) for p in pol])
                #
                # if shapely_pol.contains(Point(lp.x(), lp.y())):
                #     return True

                size = len(pol)
                for i in range(size - 1):
                    p1 = pol[i]
                    p2 = pol[i + 1]

                    d = hf.distance_from_point_to_segment(lp, p1, p2)  # hf.distance_from_point_to_line(lp, p1, p2)
                    if d < self.min_distance_to_lines:
                        self.polygon_clicked.id_pressed.emit(self.active_item.id)
                        return True
            except:
                return False

        return False

    def check_active_pressed(self, pressed_point):
        if self.active_item:
            try:
                pol = self.active_item.polygon()
                shapely_pol = Polygon([(p.x(), p.y()) for p in pol])

                if shapely_pol.contains(Point(pressed_point.x(), pressed_point.y())):
                    self.polygon_clicked.id_pressed.emit(self.active_item.id)
                    return True

                # if pol.containsPoint(pressed_point, QtCore.Qt.OddEvenFill):
                #     self.polygon_clicked.id_pressed.emit(self.active_item.id)
                #     return True
            except:
                return False

        return False

    def is_point_in_pixmap_size(self, point):
        is_in_range = True
        pixmap_width = self.pixmap_item.pixmap().width()
        pixmap_height = self.pixmap_item.pixmap().height()
        if point.x() > pixmap_width:
            is_in_range = False
        if point.x() < 0:
            is_in_range = False
        if point.y() > pixmap_height:
            is_in_range = False
        if point.y() < 0:
            is_in_range = False

        return is_in_range

    def crop_by_pixmap_size(self, item):
        pixmap_width = self.pixmap_item.pixmap().width()
        pixmap_height = self.pixmap_item.pixmap().height()
        pol = item.polygon()

        pol_new = QPolygonF()
        is_changed = False
        for p in pol:
            x = p.x()
            y = p.y()
            if p.x() > pixmap_width:
                x = pixmap_width
                is_changed = True
            if p.x() < 0:
                x = 0
                is_changed = True
            if p.y() > pixmap_height:
                x = pixmap_height
                is_changed = True
            if p.y() < 0:
                y = 0
                is_changed = True

            pol_new.append(QtCore.QPointF(x, y))

        if is_changed:
            item.setPolygon(pol_new)

    def switch_all_polygons_to_default_except_active(self):
        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                if item != self.active_item:
                    item.setBrush(QtGui.QBrush(QColor(*item.color), QtCore.Qt.SolidPattern))
                    item.setPen(QPen(QColor(*hf.set_alpha_to_max(item.color)), self.line_width, QtCore.Qt.SolidLine))
            except:
                pass

    def reset_all_polygons(self, item_clicked):
        """
        Меняем цвета и назначение полигонов на сцене в зависимости от того, по чему кликнули
        Если item_clicked был активным - снимаем активное состояние,
        еслм нет - делаем активным его, остальные - неактивными
        """
        self.toggle(item_clicked)
        self.polygon_clicked.id_pressed.emit(item_clicked.id)

        if item_clicked == self.active_item:
            self.active_item = None
        else:
            self.active_item = item_clicked
            # Остальные - в неативное состояние

            self.switch_all_polygons_to_default_except_active()

    def get_pressed_polygon(self, pressed_point):
        """
        Ищем полигон под точкой lp,
        Найдем - возвращаем полигон, не найдем - None.
        """

        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                pol = item.polygon()
                if pol.containsPoint(pressed_point, QtCore.Qt.OddEvenFill):
                    return item
            except:
                pass

        return None

    def set_ids_from_project(self, project_data):
        self.ids_worker = IdsSetterWorker(images_data=project_data['images'])
        self.ids_worker.load_ids_conn.percent.connect(self.on_load_percent_change)

        self.ids_worker.finished.connect(self.on_ids_worker_finished)

        if not self.ids_worker.isRunning():
            self.ids_worker.start()
        # self.labels_ids = []
        # self.load_ids_conn.percent.emit(0)
        # for i, im in enumerate(project_data['images']):
        #     for shape in im['shapes']:
        #         if shape['id'] not in self.labels_ids:
        #             self.labels_ids.append(shape['id'])
        #
        #     self.load_ids_conn.percent.emit(int(100 * (i + 1) / len(project_data['images'])))
        #
        # self.load_ids_conn.percent.emit(100)

    def on_load_percent_change(self, percent):
        self.load_ids_conn.percent.emit(percent)

    def on_ids_worker_finished(self):
        print('Loading project finished')
        self.labels_ids = self.ids_worker.get_labels_ids()

    def get_unique_label_id(self):
        id_tek = 0
        while id_tek in self.labels_ids:
            id_tek += 1
        self.labels_ids.append(id_tek)
        return id_tek

    def remove_label_id(self, id):
        if id in self.labels_ids:
            self.labels_ids.remove(id)

    def add_polygon_to_scene(self, cls_num, point_mass, color=None, alpha=50, id=None):
        """
        Добавление полигона на сцену
        color - цвет. Если None - будет выбран цвет, соответствующий номеру класса из config.COLORS
        alpha - прозрачность в процентах
        """

        if not point_mass:
            return

        if id == None:
            id = self.get_unique_label_id()

        if id not in self.labels_ids:
            self.labels_ids.append(id)

        polygon_new = GrPolygonLabel(None, color=color, cls_num=cls_num, alpha_percent=alpha, id=id)

        polygon_new.setBrush(QtGui.QBrush(QColor(*polygon_new.color), QtCore.Qt.SolidPattern))
        polygon_new.setPen(QPen(QColor(*hf.set_alpha_to_max(polygon_new.color)), self.line_width, QtCore.Qt.SolidLine))

        poly = QPolygonF()

        for p in point_mass:
            poly.append(QtCore.QPointF(p[0], p[1]))

        polygon_new.setPolygon(poly)

        self.scene().addItem(polygon_new)

    def addPointToActivePolygon(self, lp):

        if self.active_item:
            poly = self.active_item.polygon()
            closest_pair = hf.find_nearest_edge_of_polygon(poly, lp)
            poly_new = QPolygonF()

            size = len(poly)
            for i in range(size):
                p1 = poly[i]
                if i == size - 1:
                    p2 = poly[0]
                else:
                    p2 = poly[i + 1]

                if closest_pair == (p1, p2):
                    poly_new.append(p1)
                    closest_point = hf.get_closest_to_line_point(lp, p1, p2)
                    if closest_point:
                        poly_new.append(closest_point)

                else:
                    poly_new.append(p1)

            self.active_item.setPolygon(poly_new)
            self.crop_by_pixmap_size(self.active_item)

    def remove_polygon_vertext(self, lp):

        if self.active_item:
            point_closed = self.get_point_near_by_active_polygon_vertex(lp)

            if point_closed:

                poly_new = QPolygonF()

                pol = self.active_item.polygon()
                for p in pol:
                    if p != point_closed:
                        poly_new.append(p)

                self.active_item.setPolygon(poly_new)

    def get_active_shape(self, is_filter=True):
        if self.active_item:
            pol = self.active_item.polygon()

            if pol:
                if is_filter and len(pol) < 3:
                    self.remove_active()

                shape = {"cls_num": self.active_item.cls_num, "id": self.active_item.id}
                points = []
                for p in pol:
                    points.append([p.x(), p.y()])
                shape["points"] = points
                return shape

        return None

    def copy_active_item_to_buffer(self):
        if self.active_item:

            active_cls_num = self.active_item.cls_num
            active_alpha = self.active_item.alpha_percent
            active_color = self.active_item.color

            copy_id = self.get_unique_label_id()

            polygon_new = GrPolygonLabel(None, color=active_color, cls_num=active_cls_num,
                                         alpha_percent=active_alpha, id=copy_id)
            polygon_new.setPen(self.active_pen)
            polygon_new.setBrush(self.active_brush)
            poly = QPolygonF()
            for point in self.active_item.polygon():
                poly.append(point)

            polygon_new.setPolygon(poly)

            self.buffer = polygon_new

    def paste_buffer(self):
        if self.buffer:
            pol = self.buffer.polygon()
            xs = []
            ys = []
            for point in pol:
                xs.append(point.x())
                ys.append(point.y())
            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)
            w = abs(max_x - min_x)
            h = abs(max_y - min_y)

            pol_new = QPolygonF()
            for point in pol:
                pol_new.append(QtCore.QPointF(point.x() + w / 2, point.y() + h / 2))

            self.buffer.setPolygon(pol_new)

            if self.active_item:
                self.toggle(self.active_item)

            self.scene().addItem(self.buffer)
            self.active_item = self.buffer

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:

        modifierPressed = QApplication.keyboardModifiers()
        modifierName = ''
        # if (modifierPressed & QtCore.Qt.AltModifier) == QtCore.Qt.AltModifier:
        #     modifierName += 'Alt'

        if (modifierPressed & QtCore.Qt.ControlModifier) == QtCore.Qt.ControlModifier:
            modifierName += 'Ctrl'

        if event.buttons() == QtCore.Qt.RightButton:
            modifierName += " Right Click"

        if event.buttons() == QtCore.Qt.LeftButton:
            modifierName += " Left Click"

        sp = self.mapToScene(event.pos())
        lp = self.pixmap_item.mapFromScene(sp)

        if self.is_drawing:

            if self.drawing_type == "Polygon":

                # Режим рисования, добавляем точки к текущему полигону

                poly = self.active_item.polygon()
                poly.append(lp)
                self.active_item.setPolygon(poly)
                self.crop_by_pixmap_size(self.active_item)

            elif self.drawing_type == "Ellips":

                # Режим рисования, добавляем точки к текущему полигону

                if not self.ellips_start_point:
                    self.drag_mode = "EllipsStartDrawMode"
                    self.ellips_start_point = lp
                    self.setMouseTracking(True)

            elif self.drawing_type == "Box":

                if not self.box_start_point:
                    self.drag_mode = "BoxStartDrawMode"
                    self.box_start_point = lp
                    self.setMouseTracking(True)

            elif self.drawing_type == "AiPoints":
                if 'Left Click' in modifierName:
                    if self.is_point_in_pixmap_size(lp):
                        self.left_clicked_points.append(lp)
                        self.add_positive_ai_point_to_scene(lp)
                elif 'Right Click' in modifierName:
                    if self.is_point_in_pixmap_size(lp):
                        self.right_clicked_points.append(lp)
                        self.add_negative_ai_point_to_scene(lp)

            elif self.drawing_type == "AiMask":
                if not self.box_start_point:
                    self.drag_mode = "BoxStartDrawMode"
                    self.box_start_point = lp
                    self.setMouseTracking(True)

        else:

            if self.check_near_by_active_pressed(lp):  # нажали рядом с активным полигоном

                if self.is_close_to_fat_point(lp):
                    # Нажали по узлу

                    if 'Ctrl' in modifierName:
                        # Зажали одновременно Ctrl - убираем узел
                        self.remove_polygon_vertext(lp)

                    else:
                        # Начинаем тянуть
                        self.drag_mode = "PolygonVertexMove"
                        self.dragged_vertex = lp
                        self.setMouseTracking(False)
                else:
                    # Нажали по грани
                    if 'Ctrl' in modifierName:
                        # Добавляем узел
                        self.addPointToActivePolygon(lp)

                    else:
                        pressed_polygon = self.get_pressed_polygon(lp)
                        if pressed_polygon:
                            self.reset_all_polygons(pressed_polygon)
                        else:
                            if self.active_item:
                                self.toggle(self.active_item)
                                self.active_item = None

            else:

                # нажали не рядом с активным полигоном

                if self.check_active_pressed(lp):

                    # нажали прямо по активному полигону, строго внутри
                    # Начать перемещение,
                    # если distance_start - distance_point > threshold = переместить
                    # иначе - поменять цвет
                    self.drag_mode = "PolygonMoveMode"
                    self.start_point = lp
                    self.setMouseTracking(True)

                else:
                    # кликнули не по активной. Если по какой-то другой - изменить активную
                    pressed_polygon = self.get_pressed_polygon(lp)
                    if pressed_polygon:
                        self.reset_all_polygons(pressed_polygon)
                    else:
                        if self.active_item:
                            self.toggle(self.active_item)
                            self.active_item = None

    def get_point_near_by_active_polygon_vertex(self, point):
        scale = self._zoom / 3.0 + 1
        try:
            pol = self.active_item.polygon()
            for p in pol:
                if hf.distance(p, point) < self.fat_width / scale:
                    return p
        except:
            return None

        return None

    def add_fat_point_to_polygon_vertex(self, vertex):
        scale = self._zoom / 5.0 + 1
        self.fat_point = QtWidgets.QGraphicsEllipseItem(vertex.x() - self.fat_width / (2 * scale),
                                                        vertex.y() - self.fat_width / (2 * scale),
                                                        self.fat_width / scale, self.fat_width / scale)
        self.fat_point.setPen(self.fat_point_pen)
        self.fat_point.setBrush(self.fat_point_brush)

        self.scene().addItem(self.fat_point)

    def add_positive_ai_point_to_scene(self, point):
        scale = self._zoom / 2.5 + 1
        positive_point = QtWidgets.QGraphicsEllipseItem(point.x() - self.fat_width / (2 * scale),
                                                        point.y() - self.fat_width / (2 * scale),
                                                        self.fat_width / scale, self.fat_width / scale)
        positive_point.setPen(self.positive_point_pen)
        positive_point.setBrush(self.positive_point_brush)

        self.positive_points.append(positive_point)
        self.scene().addItem(positive_point)

    def add_negative_ai_point_to_scene(self, point):
        scale = self._zoom / 2.5 + 1
        negative_point = QtWidgets.QGraphicsEllipseItem(point.x() - self.fat_width / (2 * scale),
                                                        point.y() - self.fat_width / (2 * scale),
                                                        self.fat_width / scale, self.fat_width / scale)
        negative_point.setPen(self.negative_point_pen)
        negative_point.setBrush(self.negative_point_brush)

        self.negative_points.append(negative_point)
        self.scene().addItem(negative_point)

    def clear_ai_points(self):
        for p in self.negative_points:
            self.remove_item(p, is_delete_id=False)
        for p in self.positive_points:
            self.remove_item(p, is_delete_id=False)
        self.positive_points.clear()
        self.negative_points.clear()
        self.right_clicked_points.clear()
        self.left_clicked_points.clear()

    def remove_fat_point_from_scene(self):
        if self.fat_point:
            self.remove_item(self.fat_point, is_delete_id=False)
            self.fat_point = None

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        sp = self.mapToScene(event.pos())
        lp = self.pixmap_item.mapFromScene(sp)

        modifierPressed = QApplication.keyboardModifiers()
        modifierName = ''
        if (modifierPressed & QtCore.Qt.AltModifier) == QtCore.Qt.AltModifier:
            modifierName += 'Alt'

        if (modifierPressed & QtCore.Qt.ControlModifier) == QtCore.Qt.ControlModifier:
            modifierName += 'Ctrl'

        if 'Ctrl' in modifierName:
            if event.angleDelta().y() > 0:
                factor = 1.25
                self._zoom += 1
            else:
                factor = 0.8
                self._zoom -= 1

            if self._zoom > 0:
                self.scale(factor, factor)
                self.centerOn(lp)

            elif self._zoom == 0:
                self.fitInView(self.pixmap_item, QtCore.Qt.KeepAspectRatio)
            else:
                self._zoom = 0

    def scaleView(self, scaleFactor):
        factor = self.transform().scale(scaleFactor, scaleFactor).mapRect(QtCore.QRectF(0, 0, 1, 1)).width()
        if factor < 0.07 or factor > 100:
            return
        self.scale(scaleFactor, scaleFactor)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):

        if self.active_item:

            if self.drag_mode == "EllipsStartDrawMode" or self.drag_mode == "EllipsContinueDrawMode":
                sp = self.mapToScene(event.pos())
                lp = self.pixmap_item.mapFromScene(sp)

                width = abs(lp.x() - self.ellips_start_point.x())
                height = abs(lp.y() - self.ellips_start_point.y())

                self.active_item.setRect(self.ellips_start_point.x(), self.ellips_start_point.y(), width, height)

                self.drag_mode = "EllipsContinueDrawMode"

            elif self.drag_mode == "BoxStartDrawMode" or self.drag_mode == "BoxContinueDrawMode":
                sp = self.mapToScene(event.pos())
                lp = self.pixmap_item.mapFromScene(sp)

                width = abs(lp.x() - self.box_start_point.x())
                height = abs(lp.y() - self.box_start_point.y())

                polygon = QPolygonF()
                polygon.append(self.box_start_point)
                polygon.append(QtCore.QPointF(self.box_start_point.x() + width, self.box_start_point.y()))
                polygon.append(lp)
                polygon.append(QtCore.QPointF(self.box_start_point.x(), self.box_start_point.y() + height))

                self.active_item.setPolygon(polygon)

                self.drag_mode = "BoxContinueDrawMode"

            elif self.drag_mode == "PolygonMoveMode":
                sp = self.mapToScene(event.pos())
                lp = self.pixmap_item.mapFromScene(sp)

                delta_x = lp.x() - self.start_point.x()
                delta_y = lp.y() - self.start_point.y()
                self.start_point = lp

                poly = QPolygonF()
                for point in self.active_item.polygon():
                    point_moved = QtCore.QPointF(point.x() + delta_x, point.y() + delta_y)
                    poly.append(point_moved)

                self.active_item.setPolygon(poly)

            else:
                # Если активная - отслеживаем ее узлы

                sp = self.mapToScene(event.pos())
                lp = self.pixmap_item.mapFromScene(sp)

                self.remove_fat_point_from_scene()  # сперва убираем предыдущую точку

                point_closed = self.get_point_near_by_active_polygon_vertex(lp)
                if point_closed:
                    self.add_fat_point_to_polygon_vertex(point_closed)

                else:
                    self.remove_fat_point_from_scene()

    def change_dragged_polygon_vertex_to_point(self, new_point):
        scale = self._zoom / 3.0 + 1

        poly = QPolygonF()
        for point in self.active_item.polygon():
            if hf.distance(point, self.dragged_vertex) < self.fat_width / scale:
                poly.append(new_point)
            else:
                poly.append(point)

        self.active_item.setPolygon(poly)
        self.crop_by_pixmap_size(self.active_item)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):

        if self.drag_mode == "PolygonVertexMove":

            if self.dragged_vertex:
                sp = self.mapToScene(event.pos())
                lp = self.pixmap_item.mapFromScene(sp)

                self.change_dragged_polygon_vertex_to_point(lp)

            self.drag_mode = "No"
            self.setMouseTracking(True)

        elif self.drag_mode == "PolygonMoveMode":
            sp = self.mapToScene(event.pos())
            lp = self.pixmap_item.mapFromScene(sp)

            delta_x = lp.x() - self.start_point.x()
            delta_y = lp.y() - self.start_point.y()

            poly = QPolygonF()
            for point in self.active_item.polygon():
                point_moved = QtCore.QPointF(point.x() + delta_x, point.y() + delta_y)
                poly.append(point_moved)

            self.active_item.setPolygon(poly)

            self.crop_by_pixmap_size(self.active_item)

            self.drag_mode = "No"
            self.setMouseTracking(True)

        elif self.drag_mode == "EllipsContinueDrawMode":
            self.setMouseTracking(True)
            self.is_drawing = False
            self.ellips_start_point = None
            self.drag_mode = "No"

            if self.active_item:
                if self.active_item.check_ellips(min_width=self.min_ellips_size, min_height=self.min_ellips_size):
                    polygon_new = self.active_item.convert_to_polygon(points_count=30)
                    self.crop_by_pixmap_size(polygon_new)

                    self.remove_item(self.active_item, is_delete_id=False)
                    self.scene().addItem(polygon_new)
                    self.toggle(polygon_new)
                    self.active_item = polygon_new
                    self.polygon_end_drawing.on_end_drawing.emit(True)
                else:
                    self.remove_active()

        elif self.drag_mode == "BoxContinueDrawMode":

            self.setMouseTracking(True)
            self.is_drawing = False
            self.box_start_point = None
            self.drag_mode = "No"

            if self.active_item:
                if self.active_item.check_polygon(min_width=self.min_ellips_size,
                                                  min_height=self.min_ellips_size):
                    self.crop_by_pixmap_size(self.active_item)
                    if self.drawing_type != "AiMask":
                        self.polygon_end_drawing.on_end_drawing.emit(True)
                    else:
                        self.mask_end_drawing.on_mask_end_drawing.emit(True)

    def remove_active(self, is_delete_id=True):
        if self.active_item:
            self.remove_item(self.active_item, is_delete_id)
            self.active_item = None

    def remove_item(self, item, is_delete_id=False):

        if is_delete_id and item.id in self.labels_ids:
            self.labels_ids.remove(item.id)

        self.scene().removeItem(item)

    def remove_all_polygons(self):
        self.is_drawing = False
        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                pol = item.polygon()
                if pol:
                    self.remove_item(item, is_delete_id=True)
            except:
                pass

    def get_shapes_by_cls_num(self, cls_num, is_filter=True):
        shapes = []
        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                pol = item.polygon()

                if pol:
                    tek_cls = item.cls_num
                    if tek_cls == cls_num:
                        if is_filter and len(pol) < 3:
                            self.remove_item(item, is_delete_id=True)
                            continue

                        shape = {"cls_num": item.cls_num, "id": item.id}
                        points = []
                        for p in pol:
                            points.append([p.x(), p.y()])
                        shape["points"] = points
                        shapes.append(shape)
            except:
                pass

        return shapes

    def remove_shape_by_id(self, shape_id):
        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                pol = item.polygon()

                if pol:
                    tek_id = item.id
                    if tek_id == shape_id:
                        self.remove_item(item, is_delete_id=True)
                        return True
            except:
                pass

        return False

    def remove_shapes_by_cls(self, cls_num, is_filter=True):
        removed_count = 0
        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                pol = item.polygon()

                if pol:
                    tek_cls = item.cls_num
                    if tek_cls == cls_num:
                        self.remove_item(item, is_delete_id=True)
                        removed_count += 1
            except:
                pass

        return removed_count

    def get_shape_by_id(self, shape_id, is_filter=True):
        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                pol = item.polygon()

                if pol:
                    tek_id = item.id
                    if tek_id == shape_id:
                        if is_filter and len(pol) < 3:
                            self.remove_item(item, is_delete_id=True)
                            continue

                        shape = {"cls_num": item.cls_num, "id": item.id}
                        points = []
                        for p in pol:
                            points.append([p.x(), p.y()])
                        shape["points"] = points
                        return shape
            except:
                pass

        return None

    def get_all_shapes(self, is_filter=True):
        shapes = []

        for item in self.scene().items():
            # ищем, не попали ли уже в нарисованный полигон
            try:
                pol = item.polygon()
                if pol:

                    if is_filter and len(pol) < 3:
                        self.remove_item(item, is_delete_id=True)
                        continue

                    shape = {"cls_num": item.cls_num, "id": item.id}
                    points = []
                    for p in pol:
                        points.append([p.x(), p.y()])
                    shape["points"] = points
                    shapes.append(shape)
            except:
                pass

        return shapes

    def add_item_to_scene_as_active(self, item):
        self.active_item = item
        self.active_item.setPen(self.active_pen)
        self.active_item.setBrush(self.active_brush)
        self.scene().addItem(item)
        self.switch_all_polygons_to_default_except_active()

    def start_drawing(self, type="Polygon", cls_num=0, color=None, alpha=50, id=None):
        """
        Старт отрисовки фигуры, по умолчанию - полигона

        type - тип фигуры, по умолчанию - полигон
        cls_num - номер класса
        color - цвет. Если None - будет выбран цвет, соответствующий номеру класса из config.COLORS
        alpha - прозрачность в процентах
        """

        self.setMouseTracking(False)
        is_drawing_old = self.is_drawing
        self.is_drawing = True

        self.drawing_type = type

        if type in ["Polygon", "Box", "Ellips"]:

            if id == None:
                if is_drawing_old:
                    id = self.active_item.id
                    self.remove_active()
                else:
                    id = self.get_unique_label_id()

            if type == "Polygon" or type == "Box":
                self.active_item = GrPolygonLabel(self._pixmap_item, color=color, cls_num=cls_num, alpha_percent=alpha,
                                                  id=id)
            elif type == "Ellips":
                self.active_item = GrEllipsLabel(self._pixmap_item, color=color, cls_num=cls_num, alpha_percent=alpha,
                                                 id=id)

            self.add_item_to_scene_as_active(self.active_item)


        elif type == "AiPoints":
            self.left_clicked_points = QPolygonF()
            self.right_clicked_points = QPolygonF()

            if self.active_item:
                self.toggle(self.active_item)
                self.active_item = None

        elif type == "AiMask":

            id = self.get_unique_label_id()

            self.active_item = GrPolygonLabel(None, color=color, cls_num=cls_num, alpha_percent=alpha,
                                              id=id)

            self.add_item_to_scene_as_active(self.active_item)

    def get_sam_input_points_and_labels(self):
        if self.drawing_type == "AiPoints":
            input_point = []
            input_label = []
            for p in self.right_clicked_points:
                input_point.append([int(p.x()), int(p.y())])
                input_label.append(0)

            for p in self.left_clicked_points:
                input_point.append([int(p.x()), int(p.y())])
                input_label.append(1)

            input_point = np.array(input_point)
            input_label = np.array(input_label)

            return input_point, input_label

    def get_sam_mask_input(self):
        if self.drawing_type == "AiMask":

            if self.active_item:
                pol = self.active_item.polygon()
                if len(pol) == 4:
                    # только если бокс
                    left_top_point = pol[0]
                    right_bottom_point = pol[2]
                    input_box = np.array([int(left_top_point.x()), int(left_top_point.y()),
                                          int(right_bottom_point.x()), int(right_bottom_point.y())])

                    return input_box
                else:
                    self.remove_active()

        return []

    def end_drawing(self):
        self.is_drawing = False
        self.setMouseTracking(True)
        self.remove_fat_point_from_scene()

        if self.drawing_type in ["Polygon", "Ellips", "Box"]:

            if self.active_item:
                self.toggle(self.active_item)
                self.active_item = None
        else:
            if self.drawing_type == "AiPoints":
                self.clear_ai_points()

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        if self._pixmap_item:
            sp = self.mapToScene(event.pos())
            lp = self.pixmap_item.mapFromScene(sp)
            self.pressed_polygon = self.get_pressed_polygon(lp)
            if self.pressed_polygon:
                if self.drawing_type == "AiPoints" and self.is_drawing:
                    return
                menu = QMenu(self)
                menu.addAction(self.delPolyAct)
                menu.addAction(self.changeClsNumAct)
                menu.exec(event.globalPos())

    def on_rb_mode_change(self, is_active):
        print(f'Rubber mode: {is_active}')
        self.is_rubber_mode = is_active
        if is_active:
            self.start_drawing(type='RubberBand')
        else:
            if self.active_item and self.active_item.cls_num == -1:
                self.remove_active()
