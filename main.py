import cv2
from pyzbar.pyzbar import decode
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.graphics.texture import Texture
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.uix.popup import Popup
from kivy.core.audio import SoundLoader
import datetime
import csv
import os

# Check if the environment is Android
try:
    from jnius import autoclass
    from android.permissions import request_permissions, Permission
    request_permissions([Permission.CAMERA])
    is_android = True
except ImportError:
    is_android = False

# Set window background color
Window.clearcolor = get_color_from_hex("#f5f5f5")

class HistoryItem(BoxLayout):
    """
    A custom widget for displaying a single QR scan history item.
    """
    def __init__(self, text, qr_data, **kwargs):
        self.qr_data = qr_data
        super().__init__(orientation="horizontal", size_hint_y=None, height="40dp", **kwargs)
        
        self.is_selected = False
        self.bg_color = get_color_from_hex("#ffffff")
        self.selected_bg_color = get_color_from_hex("#e0f7fa")
        
        self.background_label = Label(text="", background_color=self.bg_color, size_hint_x=1)
        self.add_widget(self.background_label)

        self.content_label = Label(text=text, size_hint_y=1, color=get_color_from_hex("#555555"))
        self.add_widget(self.content_label)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.is_selected = not self.is_selected
            self.update_selection_color()
            return True
        return super().on_touch_down(touch)
        
    def update_selection_color(self):
        if self.is_selected:
            self.background_label.background_color = self.selected_bg_color
        else:
            self.background_label.background_color = self.bg_color

class QRScannerApp(App):
    """
    Main Kivy application class for the QR scanner.
    """
    csv_file = "qr_data.csv"
    scanned_qr_data = set()
    is_flashlight_on = False
    
    def build(self):
        print("Building the app UI...")
        self.initialize_csv()
        self.load_scanned_data()

        # Load sound files (requires 'success.mp3' and 'error.mp3' in the same directory)
        self.success_sound = SoundLoader.load("success.mp3")
        self.error_sound = SoundLoader.load("error.mp3")

        self.root_layout = BoxLayout(orientation="vertical", spacing="10dp", padding="15dp")
        
        self.camera_image = Image(size_hint_y=0.7)
        self.root_layout.add_widget(self.camera_image)
        
        self.status_label = Label(
            text="Scan a QR code",
            font_size="24sp",
            color=get_color_from_hex("#333333"),
            size_hint_y=0.1,
            halign="center"
        )
        self.root_layout.add_widget(self.status_label)
        
        self.history_layout = GridLayout(cols=1, spacing="10dp", size_hint_y=None)
        self.history_layout.bind(minimum_height=self.history_layout.setter("height"))
        
        scroll_view = ScrollView(
            size_hint=(1, 0.4),
            do_scroll_x=False,
            bar_color=[0.6, 0.6, 0.6, 0.9],
            bar_width="5dp"
        )
        scroll_view.add_widget(self.history_layout)
        self.root_layout.add_widget(scroll_view)
        
        self.button_layout = GridLayout(cols=3, spacing="10dp", size_hint_y=0.15)
        
        self.start_button = Button(text="Start Scan", background_color=get_color_from_hex("#4caf50"), color=get_color_from_hex("#ffffff"), font_size="16sp")
        self.start_button.bind(on_press=self.start_camera)
        
        self.stop_button = Button(text="Stop Scan", background_color=get_color_from_hex("#ff9800"), color=get_color_from_hex("#ffffff"), font_size="16sp")
        self.stop_button.bind(on_press=self.stop_camera)

        self.exit_button = Button(text="Exit App", background_color=get_color_from_hex("#f44336"), color=get_color_from_hex("#ffffff"), font_size="16sp")
        self.exit_button.bind(on_press=self.stop)
        
        self.flashlight_button = Button(text="Flashlight", background_color=get_color_from_hex("#2196f3"), color=get_color_from_hex("#ffffff"), font_size="16sp")
        self.flashlight_button.bind(on_press=self.toggle_flashlight)
        
        self.select_all_button = Button(text="Select All", background_color=get_color_from_hex("#607d8b"), color=get_color_from_hex("#ffffff"), font_size="16sp")
        self.select_all_button.bind(on_press=self.select_all_history)
        
        self.delete_selected_button = Button(text="Delete Selected", background_color=get_color_from_hex("#e91e63"), color=get_color_from_hex("#ffffff"), font_size="16sp")
        self.delete_selected_button.bind(on_press=self.delete_selected_history)
        
        self.button_layout.add_widget(self.start_button)
        self.button_layout.add_widget(self.stop_button)
        self.button_layout.add_widget(self.exit_button)
        self.button_layout.add_widget(self.flashlight_button)
        self.button_layout.add_widget(self.select_all_button)
        self.button_layout.add_widget(self.delete_selected_button)
        
        self.root_layout.add_widget(self.button_layout)
        
        self.cap = None
        self.event = None
        
        return self.root_layout

    def on_start(self):
        print("App started. Loading history...")
        self.update_history_display()

    def start_camera(self, *args):
        print("Start Scan button pressed.")
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
            if self.cap and self.cap.isOpened():
                self.event = Clock.schedule_interval(self.update_frame, 1.0/30.0)
                self.status_label.text = "Scanning..."
                self.status_label.color = get_color_from_hex("#333333")
                print("Camera successfully started.")
            else:
                self.status_label.text = "Error: Camera not found."
                self.status_label.color = get_color_from_hex("#ff0000")
                print("Error: Could not open camera.")
        else:
            print("Camera is already running.")

    def stop_camera(self, *args):
        print("Stop Scan button pressed.")
        if self.event:
            self.event.cancel()
            self.event = None
            print("Clock event for frame updates cancelled.")
        if self.cap:
            self.cap.release()
            self.cap = None
            self.camera_image.texture = None
            print("Camera released.")
        
        if self.is_flashlight_on:
            self.toggle_flashlight()
        
        self.status_label.text = "Scan stopped."
        self.status_label.color = get_color_from_hex("#ff0000")

    def update_frame(self, dt):
        ret, frame = self.cap.read()
        if not ret:
            print("Error: Could not read frame from camera.")
            return

        frame = cv2.flip(frame, 1)
        decoded_objects = decode(frame)

        if decoded_objects:
            obj = decoded_objects[0]
            qr_data = obj.data.decode("utf-8").strip()

            if qr_data in self.scanned_qr_data:
                self.status_label.text = "❌ Already Scanned"
                self.status_label.color = get_color_from_hex("#ff0000")
                if self.error_sound:
                    self.error_sound.play()
            else:
                self.scanned_qr_data.add(qr_data)
                self.status_label.text = "✅ Scan Successful!"
                self.status_label.color = get_color_from_hex("#00aa00")
                if self.success_sound:
                    self.success_sound.play()
                
                self.show_popup(qr_data)
                
        buf1 = cv2.flip(frame, 0)
        buf = buf1.tobytes()
        image_texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt="bgr")
        image_texture.blit_buffer(buf, colorfmt="bgr", bufferfmt="ubyte")
        self.camera_image.texture = image_texture

    def show_popup(self, qr_data):
        print(f"Showing popup for data: {qr_data}")
        content = BoxLayout(orientation='vertical', spacing='10dp', padding='10dp')
        
        now = datetime.datetime.now()
        try:
            with open(self.csv_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([qr_data, now.date(), now.time().strftime("%H:%M:%S"), "success"])
        except Exception as e:
            print(f"Error writing to CSV: {e}")
        
        self.update_history_display()
        popup_title = "Scan Result"
        popup_text = f"Data: {qr_data}\n\nDate: {now.date()}\nTime: {now.time().strftime('%H:%M:%S')}"
        
        content.add_widget(Label(text=popup_text, size_hint_y=None, height='50dp', font_size='18sp'))
        
        close_button = Button(text="Close", size_hint_y=None, height='40dp', background_color=get_color_from_hex("#2196f3"))
        content.add_widget(close_button)

        popup = Popup(title=popup_title, content=content, size_hint=(0.8, 0.4), auto_dismiss=False)
        close_button.bind(on_press=popup.dismiss)
        popup.open()
        
        self.stop_camera()

    def initialize_csv(self):
        print("Initializing CSV file...")
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Data", "Date", "Time", "Status"])
            print("CSV file created.")

    def load_scanned_data(self):
        print("Loading scanned data from CSV...")
        try:
            with open(self.csv_file, "r") as f:
                for row in csv.DictReader(f):
                    self.scanned_qr_data.add(row["Data"].strip())
            print("Scanned data loaded.")
        except FileNotFoundError:
            print("CSV file not found, no data loaded.")

    def update_history_display(self):
        print("Updating history display...")
        self.history_layout.clear_widgets()
        try:
            with open(self.csv_file, "r") as f:
                lines = f.readlines()
                for line in reversed(lines[1:]):
                    row = line.strip().split(",")
                    if len(row) >= 3:
                        qr_data = row[0]
                        history_text = f"[{row[1]} {row[2]}] {qr_data}"
                        item = HistoryItem(history_text, qr_data=qr_data)
                        self.history_layout.add_widget(item)
        except FileNotFoundError:
            print("History CSV file not found.")

    def select_all_history(self, *args):
        print("Select All button pressed.")
        for item in self.history_layout.children:
            if not item.is_selected:
                item.is_selected = True
                item.update_selection_color()
        self.status_label.text = "All items selected."
        self.status_label.color = get_color_from_hex("#333333")

    def delete_selected_history(self, *args):
        print("Delete Selected button pressed.")
        items_to_delete = [item for item in self.history_layout.children if item.is_selected]
        if not items_to_delete:
            self.status_label.text = "No items selected for deletion."
            self.status_label.color = get_color_from_hex("#ff0000")
            print("No items selected.")
            return
            
        current_data = []
        try:
            with open(self.csv_file, "r") as f:
                reader = csv.reader(f)
                header = next(reader)
                current_data.append(header)
                
                deleted_count = 0
                for row in reader:
                    if row[0] not in [item.qr_data for item in items_to_delete]:
                        current_data.append(row)
                    else:
                        deleted_count += 1

            with open(self.csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(current_data)
            
            for item in items_to_delete:
                self.scanned_qr_data.discard(item.qr_data)
            
            self.update_history_display()
            self.status_label.text = f"{deleted_count} items deleted!"
            self.status_label.color = get_color_from_hex("#00aa00")
            print(f"{deleted_count} items successfully deleted.")

        except Exception as e:
            print(f"Error during deletion: {e}")
            self.status_label.text = "Error deleting items."
            self.status_label.color = get_color_from_hex("#ff0000")

    def toggle_flashlight(self, *args):
        print("Flashlight button pressed.")
        if not is_android:
            print("Flashlight functionality is only available on Android.")
            return

        try:
            Context = autoclass('android.content.Context')
            CameraManager = autoclass('android.hardware.camera2.CameraManager')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            context = PythonActivity.mActivity
            camera_manager = context.getSystemService(Context.CAMERA_SERVICE)
            camera_id = camera_manager.getCameraIdList()[0]

            if not self.is_flashlight_on:
                camera_manager.setTorchMode(camera_id, True)
                self.flashlight_button.text = "Flashlight (On)"
                self.is_flashlight_on = True
                print("Flashlight turned on.")
            else:
                camera_manager.setTorchMode(camera_id, False)
                self.flashlight_button.text = "Flashlight (Off)"
                self.is_flashlight_on = False
                print("Flashlight turned off.")
        except Exception as e:
            print(f"Failed to toggle flashlight: {e}")
    
    def on_stop(self):
        print("App is stopping. Releasing camera resources.")
        self.stop_camera()

if __name__ == "__main__":
    QRScannerApp().run()
