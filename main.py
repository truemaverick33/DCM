import re
import sys
import subprocess
import time
from datetime import datetime, timedelta
from threading import Thread
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import seaborn as sns
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QWidget, QLabel, QTabWidget, QMenuBar, QToolBar, QDialog, QFormLayout,
    QDialogButtonBox, QCheckBox, QHeaderView, QTextEdit
)
from PyQt6.QtGui import QIcon, QAction
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class ContainerMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Docker Container Monitor")
        self.setGeometry(100, 100, 800, 800)

        # Universal stats configuration
        self.active_stats = {"CPU": True, "Memory": True, "Network I/O": False, "Disk I/O": False}

        self.init_ui()

    def init_ui(self):
        # Main layout with tabs
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tabs)

        # Menu bar
        self.menu_bar = self.menuBar()
        view_menu = self.menu_bar.addMenu("View")

        # Recreate Containers tab
        recreate_action = QAction("Show Containers", self)
        recreate_action.triggered.connect(self.recreate_containers_tab)
        view_menu.addAction(recreate_action)

        # Recreate Network Tab
        network_activity_action = QAction("Show Network Activity", self)
        network_activity_action.triggered.connect(self.recreate_network_tab)
        view_menu.addAction(network_activity_action)

        # Preferences submenu
        preferences_action = QAction("Preferences...", self)
        preferences_action.triggered.connect(self.open_configure_dialog)
        view_menu.addAction(preferences_action)

        # Toolbar with buttons
        self.toolbar = QToolBar(self)
        self.addToolBar(self.toolbar)

        # Refresh button
        refresh_action = QAction(QIcon("refresh.ico"), "Refresh Containers", self)
        refresh_action.triggered.connect(self.load_containers)
        self.toolbar.addAction(refresh_action)

        # Network graph button
        network_graph_action = QAction(QIcon("network.ico"), "Network Graph", self)
        network_graph_action.triggered.connect(self.plot_network_graph)
        self.toolbar.addAction(network_graph_action)
        
        #IP connection heatmap
        heat_graph_action = QAction(QIcon("heatmap.ico"), "Heatmap", self)
        heat_graph_action.triggered.connect(self.plot_connection_heatmap)
        self.toolbar.addAction(heat_graph_action)

        # Tab for listing all containers
        self.container_list_tab = QWidget()
        self.container_list_layout = QVBoxLayout()
        self.container_list_tab.setLayout(self.container_list_layout)
        self.tabs.addTab(self.container_list_tab, "Containers")

        # Table to display containers
        self.container_table = QTableWidget()
        self.container_list_layout.addWidget(self.container_table)
        self.container_table.setColumnCount(5)
        self.container_table.setHorizontalHeaderLabels(["Container ID", "Container Name", "Image Name", "Status", "Command"])
        self.container_table.cellClicked.connect(self.container_clicked)

        self.load_containers()

        self.network_tab = None
        self.recreate_network_tab()

    def load_containers(self):
        # Clear the table
        self.container_table.setRowCount(0)

        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Command}}"],
                stdout=subprocess.PIPE,
                text=True,
                check=True
            )
            containers = result.stdout.strip().split("\n")
        except subprocess.CalledProcessError as e:
            containers = []
            print(f"Error fetching containers: {e}")

        # Populate the table with container data
        for i, line in enumerate(containers):
            if line.strip():
                container_data = line.split("|")
                self.container_table.insertRow(i)
                for j, data in enumerate(container_data):
                    self.container_table.setItem(i, j, QTableWidgetItem(data))

    def container_clicked(self, row, column):
        container_id = self.container_table.item(row, 0).text()
        container_name = self.container_table.item(row, 1).text()
        self.open_stats_tab(container_id, container_name)

    def open_stats_tab(self, container_id, container_name):
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == container_name:
                self.tabs.setCurrentIndex(i)
                return

        stats_tab = StatsTab(container_id, container_name, self.active_stats)
        self.tabs.addTab(stats_tab, container_name)
        self.tabs.setCurrentWidget(stats_tab)

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        if isinstance(widget, StatsTab):
            widget.stop_timer()
        self.tabs.removeTab(index)

    def recreate_containers_tab(self):
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Containers":
                return

        self.container_list_tab = QWidget()
        self.container_list_layout = QVBoxLayout()
        self.container_list_tab.setLayout(self.container_list_layout)
        self.tabs.addTab(self.container_list_tab, "Containers")
        self.load_containers()

    def recreate_network_tab(self):
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Network Connections":
                return
        self.network_tab = NetworkTab()
        self.tabs.addTab(self.network_tab, "Network Connections")
        self.tabs.setCurrentWidget(self.network_tab)

    def on_tab_changed(self, index):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, StatsTab):
                if i == index:
                    widget.start_timer()
                else:
                    widget.stop_timer()

    def open_configure_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure Stats")
        layout = QFormLayout(dialog)

        checkboxes = {}
        for stat in self.active_stats.keys():
            checkbox = QCheckBox(stat)
            checkbox.setChecked(self.active_stats[stat])
            checkboxes[stat] = checkbox
            layout.addRow(stat, checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(lambda: self.apply_changes(dialog, checkboxes))
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        dialog.exec()

    def apply_changes(self, dialog, checkboxes):
        for stat, checkbox in checkboxes.items():
            self.active_stats[stat] = checkbox.isChecked()
        dialog.accept()

    def plot_network_graph(self):
        if not self.network_tab:
            return

        # Extract IPs from the network table
        data = []
        for row in range(self.network_tab.network_table.rowCount()):
            timestamp = self.network_tab.network_table.item(row, 0).text()
            source_ip = self.network_tab.network_table.item(row, 1).text()
            dest_ip = self.network_tab.network_table.item(row, 2).text()
            data.append([timestamp, source_ip, dest_ip])

        if not data:
            print("No network data available to plot.")
            return

        # Create a DataFrame
        df = pd.DataFrame(data, columns=["Timestamp", "Source IP", "Destination IP"])

        # Create a graph
        G = nx.Graph()

        # Count connections between each unique IP pair
        connection_counts = df.groupby(['Source IP', 'Destination IP']).size().reset_index(name='Count')

        # Add edges to the graph with connection counts as weights
        for _, row in connection_counts.iterrows():
            G.add_edge(row['Source IP'], row['Destination IP'], weight=row['Count'])

        # Draw the network graph
        plt.figure(figsize=(10, 8))

        # Set edge thickness based on connection frequency
        edges = G.edges(data=True)
        edge_weights = [edge_data['weight'] for _, _, edge_data in edges]

        # Draw the graph with node and edge configurations
        pos = nx.spring_layout(G, k=0.5)  # Layout for visualization
        nx.draw_networkx_nodes(G, pos, node_size=500, node_color="skyblue")
        nx.draw_networkx_edges(G, pos, width=edge_weights, alpha=0.5, edge_color="gray")
        nx.draw_networkx_labels(G, pos, font_size=10, font_family="sans-serif")

        # Add title and show plot
        plt.title("Network Graph of IP Connections")
        plt.axis("off")
        plt.tight_layout()
        plt.show()

    def plot_connection_heatmap(self):
        if not self.network_tab:
            return

        # Extract IPs and timestamps from the network table
        data = []
        for row in range(self.network_tab.network_table.rowCount()):
            timestamp = self.network_tab.network_table.item(row, 0).text()
            source_ip = self.network_tab.network_table.item(row, 1).text()
            dest_ip = self.network_tab.network_table.item(row, 2).text()
            data.append([timestamp, source_ip, dest_ip])

        if not data:
            print("No network data available to plot.")
            return

        # Create a DataFrame
        df = pd.DataFrame(data, columns=["Timestamp", "Source IP", "Destination IP"])

        # Convert the 'Timestamp' column to datetime format
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])

        # Create a unique connection label
        df['Connection'] = df['Source IP'] + " -> " + df['Destination IP']

        # Resample data by minute to get connection counts
        connection_counts = df.groupby(['Connection']).resample('1T', on='Timestamp').size().unstack(fill_value=0)

        if connection_counts.empty:
            print("No connection data available for the heatmap.")
            return

        # Plot heatmap
        plt.figure(figsize=(12, 8))
        sns.heatmap(connection_counts, cmap="YlGnBu", annot=False, cbar=True)

        # Set plot labels and title
        plt.title("Heatmap of IP Connection Counts Over Time")
        plt.xlabel("Time")
        plt.ylabel("IP Connections (Source -> Destination)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

class StatsTab(QWidget):
    def __init__(self, container_id, container_name, active_stats):
        super().__init__()
        self.container_id = container_id
        self.container_name = container_name
        self.active_stats = active_stats
        self.last_fetch_time = datetime.utcnow() - timedelta(seconds=10)
        self.is_first_fetch = True

        # Variables to store stats over time
        self.stats_data = pd.DataFrame(columns=['Timestamp', 'CPU %', 'Memory %'])

        # UI initialization
        self.init_ui()

        # Worker thread for stats fetching
        self.running = True
        self.thread = Thread(target=self.fetch_stats, daemon=True)
        self.thread.start()
        
        #self.running = True
        #self.thread = Thread(target=self.fetch_logs, daemon=True)
        #self.thread.start()

    def init_ui(self):
        # Create the main layout
        layout = QVBoxLayout()

        # Add a label to show current stats
        self.stats_label = QLabel("Fetching stats...")
        layout.addWidget(self.stats_label)
        
        # Add a text area to display logs
        self.logs_area = QTextEdit()
        self.logs_area.setPlaceholderText("Fetching Logs...")
        self.logs_area.setReadOnly(True)
        layout.addWidget(self.logs_area)
        
        # Add a Matplotlib canvas for the graph
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.setLayout(layout)

    def fetch_stats(self):
        while self.running:
            try:
                format_parts = []
                if self.active_stats.get("CPU"):
                    format_parts.append("CPU: {{.CPUPerc}}")
                if self.active_stats.get("Memory"):
                    format_parts.append("Memory: {{.MemPerc}}")
                if self.active_stats.get("Network I/O"):
                    format_parts.append("Network I/O: {{.NetIO}}")
                if self.active_stats.get("Disk I/O"):
                    format_parts.append("Disk I/O: {{.BlockIO}}")

                format_string = " | ".join(format_parts)
                cmd = ["docker", "stats", self.container_id, "--no-stream", "--format", format_string]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
                self.process_stats(result.stdout.strip())
            except subprocess.CalledProcessError as e:
                self.update_stats_label(f"Error fetching stats: {e}")
            time.sleep(2)
            
    def process_stats(self, raw_stats):
        try:
            # Parse the stats
            stats_parts = raw_stats.split(" | ")
            stats_dict = {}
            for part in stats_parts:
                key, value = part.split(": ")
                stats_dict[key.strip()] = value.strip()

            # Extract CPU and Memory usage
            cpu_usage = float(stats_dict.get("CPU", "0%").replace("%", ""))
            memory_usage = float(stats_dict.get("Memory", "0%").replace("%", ""))
            timestamp = datetime.now()

            # Update the DataFrame
            new_row = {'Timestamp': timestamp, 'CPU %': cpu_usage, 'Memory %': memory_usage}
            self.stats_data = pd.concat([self.stats_data, pd.DataFrame([new_row])], ignore_index=True)

            # Update the stats label
            self.update_stats_label(raw_stats)
            self.fetch_logs()
            
            # Update the graph every 10 seconds
            if len(self.stats_data) % 2 == 0:
                self.update_graph()
                self.fetch_logs()

        except Exception as e:
            self.update_stats_label(f"Error processing stats: {e}")
            
    def fetch_logs(self):
            if self.is_first_fetch:
            # First fetch: Get all logs
                cmd = ["docker", "logs", "-t", self.container_id]
                self.is_first_fetch = False
            else:
            # Subsequent fetches: Fetch logs since last time
                since_time = self.last_fetch_time.isoformat() + "Z"
                cmd = ["docker", "logs", "--since", since_time, "-t", self.container_id]

            result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
            self.last_fetch_time = datetime.utcnow()
            new_logs = result.stdout.strip()
            if new_logs:
                self.logs_area.append(new_logs)

    def update_stats_label(self, text):
        self.stats_label.setText(text)

    def update_graph(self):
        try:
            # Clear the previous plot
            self.figure.clear()

            # Add a subplot
            ax = self.figure.add_subplot(111)

            # Plot the CPU and Memory usage
            if not self.stats_data.empty:
                ax.plot(self.stats_data['Timestamp'], self.stats_data['CPU %'], label='CPU Usage (%)', color='blue')
                ax.plot(self.stats_data['Timestamp'], self.stats_data['Memory %'], label='Memory Usage (%)', color='orange')

                # Format the plot
                ax.set_title(f"Resource Usage Over Time for Container: {self.container_name}")
                ax.set_xlabel("Time")
                ax.set_ylabel("Usage (%)")
                ax.legend(loc="upper right")
                ax.grid()

            # Refresh the canvas
            self.canvas.draw()

        except Exception as e:
            print(f"Error updating graph: {e}")

    def start_timer(self):
        if not self.thread.is_alive():  # Check if the thread is already running
            self.running = True
            self.thread = Thread(target=self.fetch_stats, daemon=True)  # Recreate the thread if not alive
            self.thread.start()

    def stop_timer(self):
        self.running = False

class NetworkTab(QWidget):
    def __init__(self):
        super().__init__()
        self.docker_interface = "docker0"
        self.ip_pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+)')
        self.init_ui()

        # Worker thread for capturing network activity
        self.running = True
        self.thread = Thread(target=self.capture_ips, daemon=True)
        self.thread.start()

    def init_ui(self):
        layout = QVBoxLayout()
        self.network_table = QTableWidget()
        self.network_table.setColumnCount(3)
        self.network_table.setHorizontalHeaderLabels(["Timestamp", "Source IP", "Destination IP"])
        self.network_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.network_table)
        self.setLayout(layout)

    def capture_ips(self):
        try:
            process = subprocess.Popen(
                ["sudo", "tcpdump", "-i", self.docker_interface, "-n", "-l"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            while self.running:
                line = process.stdout.readline()
                if not line:
                    break

                ips = self.ip_pattern.findall(line)
                if len(ips) >= 2:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.add_network_row(timestamp, ips[0], ips[1])
        except Exception as e:
            print(f"Error capturing network data: {e}")

    def add_network_row(self, timestamp, source_ip, dest_ip):
        row = self.network_table.rowCount()
        self.network_table.insertRow(row)
        self.network_table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.network_table.setItem(row, 1, QTableWidgetItem(source_ip))
        self.network_table.setItem(row, 2, QTableWidgetItem(dest_ip))

    def stop_capture(self):
        self.running = False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ContainerMonitor()
    window.show()
    sys.exit(app.exec())


