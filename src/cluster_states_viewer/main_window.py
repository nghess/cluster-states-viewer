from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import config
from .place_field_worker import PlaceFieldWorker
from .plot_widget import EpochPlaceFieldPlot, PlaceFieldPlot
from .session_data import ClusterSessionData, discover_sessions

COLUMNS = ["Cluster", "Region", "Label", "Ch", "N Spikes", "SI"]


class NumericTableWidgetItem(QTableWidgetItem):
    """Sorts by a numeric value while displaying arbitrary text (e.g. '-')."""

    def __init__(self, value: float, text: str | None = None):
        super().__init__(text if text is not None else str(value))
        self.value = value

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return bool(self.value < other.value)
        return super().__lt__(other)


class MainWindow(QMainWindow):
    def __init__(self, data_root: Path = config.DEFAULT_DATA_ROOT):
        super().__init__()
        self.setWindowTitle("Cluster States Viewer")
        self.resize(1500, 900)

        self.data_root = data_root
        self.sessions = discover_sessions(data_root)  # (animal, session, events_path, hc_dir, ob_dir)
        self.session: ClusterSessionData | None = None
        self.worker: PlaceFieldWorker | None = None
        self._cluster_by_key = {}
        self._region_warning = ""

        self._build_ui()
        self._populate_animals()

    # ----- UI construction -----------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        picker_row = QHBoxLayout()
        self.animal_combo = QComboBox()
        self.session_combo = QComboBox()
        self.load_button = QPushButton("Load")
        self.status_label = QLabel("")
        picker_row.addWidget(QLabel("Animal:"))
        picker_row.addWidget(self.animal_combo)
        picker_row.addWidget(QLabel("Session:"))
        picker_row.addWidget(self.session_combo)
        picker_row.addWidget(self.load_button)
        picker_row.addSpacing(12)
        picker_row.addWidget(self.status_label)
        picker_row.addStretch(1)
        root.addLayout(picker_row)

        self.animal_combo.currentTextChanged.connect(self._populate_sessions)
        self.load_button.clicked.connect(self._load_selected_session)

        # main split: place-field plot | cluster table
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        self.plot_tabs = QTabWidget()
        self.flip_state_plot = PlaceFieldPlot()
        self.epoch_plot = EpochPlaceFieldPlot()
        self.plot_tabs.addTab(self.flip_state_plot, "Flip State")
        self.plot_tabs.addTab(self.epoch_plot, "Epoch")
        splitter.addWidget(self.plot_tabs)

        self.cluster_table = QTableWidget(0, len(COLUMNS))
        self.cluster_table.setHorizontalHeaderLabels(COLUMNS)
        self.cluster_table.setMaximumWidth(560)
        self.cluster_table.setSortingEnabled(True)
        self.cluster_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # currentCellChanged (not cellClicked) so up/down-arrow row navigation
        # updates the plot too, not just mouse clicks.
        self.cluster_table.currentCellChanged.connect(self._on_current_cell_changed)
        splitter.addWidget(self.cluster_table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

    # ----- session/animal population --------------------------------------
    def _populate_animals(self):
        animals = sorted({a for a, _, _, _, _ in self.sessions})
        self.animal_combo.addItems(animals)

    def _populate_sessions(self, animal: str):
        self.session_combo.clear()
        sessions = sorted(s for a, s, _, _, _ in self.sessions if a == animal)
        self.session_combo.addItems(sessions)

    def _load_selected_session(self):
        animal = self.animal_combo.currentText()
        session_name = self.session_combo.currentText()
        match = next((row for row in self.sessions
                      if row[0] == animal and row[1] == session_name), None)
        if match is None:
            return
        _animal, _session, events_path, hc_dir, ob_dir = match

        if self.worker is not None and self.worker.isRunning():
            self.worker.wait()

        self.load_button.setEnabled(False)
        self.cluster_table.setRowCount(0)
        self.flip_state_plot.set_cluster(None, None)
        self.epoch_plot.set_cluster(None, None)
        self.status_label.setStyleSheet("")
        self.status_label.setText("Loading session...")
        # let the label paint before the (synchronous) session load below
        self.repaint()

        self.session = ClusterSessionData(animal, session_name, events_path, hc_dir, ob_dir)

        self._region_warning = ""
        if self.session.uncurated_regions:
            regions = ', '.join(r.upper() for r in self.session.uncurated_regions)
            self._region_warning = (f"  [no phy curation for {regions} - "
                                     f"labels are Kilosort's automatic KSLabel only]")
            self.status_label.setStyleSheet("color: orange;")

        if not self.session.clusters:
            self.status_label.setText("No good/mua clusters found for this session." + self._region_warning)
            self.load_button.setEnabled(True)
            return

        self.status_label.setText(
            f"Computing place fields... (0/{len(self.session.clusters)})" + self._region_warning)
        self.worker = PlaceFieldWorker(self.session, parent=self)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.finished_ok.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_progress(self, done: int, total: int):
        self.status_label.setText(f"Computing place fields... ({done}/{total})" + self._region_warning)

    def _on_worker_finished(self, clusters):
        self.status_label.setText(f"{len(clusters)} clusters loaded." + self._region_warning)
        self.load_button.setEnabled(True)
        self._populate_cluster_table(clusters)

    def _populate_cluster_table(self, clusters):
        self.cluster_table.setSortingEnabled(False)  # avoid resorting mid-populate
        self.cluster_table.setRowCount(len(clusters))
        self._cluster_by_key = {(c.region, c.cluster_id): c for c in clusters}

        for row, cluster in enumerate(clusters):
            id_item = NumericTableWidgetItem(cluster.cluster_id)
            id_item.setData(Qt.UserRole, (cluster.region, cluster.cluster_id))
            self.cluster_table.setItem(row, 0, id_item)
            self.cluster_table.setItem(row, 1, QTableWidgetItem(cluster.region.upper()))
            self.cluster_table.setItem(row, 2, QTableWidgetItem(cluster.label))

            ch = cluster.best_channel
            self.cluster_table.setItem(row, 3, NumericTableWidgetItem(
                ch if ch is not None else -1, str(ch) if ch is not None else "-"))
            self.cluster_table.setItem(row, 4, NumericTableWidgetItem(cluster.n_spikes))
            self.cluster_table.setItem(row, 5, NumericTableWidgetItem(cluster.si, f"{cluster.si:.3f}"))

        self.cluster_table.resizeColumnsToContents()
        self.cluster_table.setSortingEnabled(True)

    def _on_current_cell_changed(self, row: int, _col: int, _prev_row: int, _prev_col: int):
        if self.session is None or row < 0:
            return
        key = self.cluster_table.item(row, 0).data(Qt.UserRole)
        cluster = self._cluster_by_key.get(key)
        if cluster is not None:
            title = (f"{self.session.animal} {self.session.session}  |  "
                     f"Cluster {cluster.cluster_id} ({cluster.region.upper()})")
            self.flip_state_plot.set_cluster(self.session, cluster, title=title)
            self.epoch_plot.set_cluster(self.session, cluster, title=title)
