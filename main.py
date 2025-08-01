import tkinter as tk
from tkinter import ttk, messagebox
import mido
import json
import os

CONFIG_FILE = "midi_config.json"
NUM_FADERS = 6

class MidiControllerApp:
    def __init__(self, root):
        self.root = root
        root.title("Контроллер Zoom L6")
        root.configure(bg="#2b2b2b")

        self.assigned_controls = {}
        self.fader_scales = []
        self.panorama_scales = []
        self.effect_scales = []
        self.mute_buttons = []
        self.mute_states = [False] * NUM_FADERS

        self.midi_in_port = None
        self.midi_out_port = None

        self.midi_assign_mode = False
        self.current_assign_target = None
        self.assign_window = None  # Окно назначения

        self.loaded_config_data = None
        self.compressor_state = False

        self.build_gui()
        self.load_config()
        self.refresh_ports()
        self.set_ports_from_config()
        self.connect_ports()
        self.apply_loaded_values()
        self.send_all_controls_to_device()

    def build_gui(self):
        # Настройка grid для root
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)  # строка с фейдерами будет растягиваться

        self.status_label = tk.Label(self.root, text="Выберите MIDI-порты", fg="lightgray", bg="#2b2b2b", font=("Segoe UI", 10))
        self.status_label.grid(row=0, column=0, sticky="ew", pady=5)

        frame_ports = tk.Frame(self.root, bg="#2b2b2b")
        frame_ports.grid(row=1, column=0, sticky="ew", padx=5)
        frame_ports.grid_columnconfigure(1, weight=1)

        tk.Label(frame_ports, text="MIDI IN:", fg="white", bg="#2b2b2b").grid(row=0, column=0, sticky="e")
        self.in_var = tk.StringVar()
        self.in_combo = ttk.Combobox(frame_ports, textvariable=self.in_var, width=40, state="readonly")
        self.in_combo.grid(row=0, column=1, padx=5, sticky="ew")

        tk.Label(frame_ports, text="MIDI OUT:", fg="white", bg="#2b2b2b").grid(row=1, column=0, sticky="e")
        self.out_var = tk.StringVar()
        self.out_combo = ttk.Combobox(frame_ports, textvariable=self.out_var, width=40, state="readonly")
        self.out_combo.grid(row=1, column=1, padx=5, sticky="ew")

        btn_refresh = tk.Button(frame_ports, text="Обновить", command=self.refresh_ports, bg="#444", fg="white")
        btn_refresh.grid(row=0, column=2, rowspan=2, padx=5, sticky="ns")

        btn_connect = tk.Button(frame_ports, text="Подключиться", command=self.connect_ports, bg="#4a90e2", fg="white")
        btn_connect.grid(row=0, column=3, rowspan=2, padx=5, sticky="ns")

        frame_faders = tk.Frame(self.root, bg="#2b2b2b")
        frame_faders.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        frame_faders.grid_rowconfigure(0, weight=1)

        for i in range(NUM_FADERS):
            col = tk.Frame(frame_faders, bg="#3c3c3c", bd=2, relief="raised")
            col.grid(row=0, column=i, sticky="nsew", padx=6)
            frame_faders.grid_columnconfigure(i, weight=1)

            # Настройка grid для колонки с каналом
            for r in range(12):
                col.grid_rowconfigure(r, weight=0)
            col.grid_rowconfigure(1, weight=1)  # Фейдер громкости растягивается вертикально
            col.grid_columnconfigure(0, weight=1)

            tk.Label(col, text=f"Канал {i+1}", bg="#3c3c3c", fg="white", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, pady=(8,6))

            # Вертикальный фейдер громкости без надписи
            scale = tk.Scale(col, from_=100, to=0, orient=tk.VERTICAL,
                             fg="white", bg="#3c3c3c", troughcolor="#6b6b6b",
                             highlightthickness=0, relief="flat", font=("Segoe UI", 8))
            scale.grid(row=1, column=0, sticky="nsew", pady=(0,8), padx=10)
            scale.config(command=self.make_fader_callback(i))
            self.bind_save_on_release(scale)
            self.fader_scales.append(scale)

            # Иконка шестерёнки для назначения фейдера
            btn_assign_fader = tk.Canvas(col, width=20, height=20, bg="#3c3c3c", highlightthickness=0)
            btn_assign_fader.grid(row=2, column=0)
            self.draw_gear_icon(btn_assign_fader, 10, 10, 8, fill="#bbbbbb")
            btn_assign_fader.bind("<Button-1>", lambda e, c=f"fader_{i}": self.open_assign_window(c))

            # Кнопка Mute — красная при активном состоянии
            mute_btn = tk.Button(col, width=8, command=self.make_toggle_mute(i))
            mute_btn.grid(row=3, column=0, pady=6)
            self.mute_buttons.append(mute_btn)
            self.update_mute_button(i)

            # Иконка шестерёнки для назначения Mute
            btn_assign_mute = tk.Canvas(col, width=20, height=20, bg="#3c3c3c", highlightthickness=0)
            btn_assign_mute.grid(row=4, column=0)
            self.draw_gear_icon(btn_assign_mute, 10, 10, 8, fill="#bbbbbb")
            btn_assign_mute.bind("<Button-1>", lambda e, c=f"mute_{i}": self.open_assign_window(c))

            # Панорама
            pan_label = tk.Label(col, text="Панорама", bg="#3c3c3c", fg="white", font=("Segoe UI", 8))
            pan_label.grid(row=5, column=0, pady=(10,0))
            pan = tk.Scale(col, from_=-100, to=100, orient=tk.HORIZONTAL,
                           fg="white", bg="#3c3c3c", troughcolor="#6b6b6b",
                           highlightthickness=0, relief="flat", font=("Segoe UI", 8))
            pan.grid(row=6, column=0, sticky="ew", padx=5)
            pan.config(command=self.make_panorama_callback(i))
            self.bind_save_on_release(pan)
            self.panorama_scales.append(pan)

            btn_assign_pan = tk.Canvas(col, width=20, height=20, bg="#3c3c3c", highlightthickness=0)
            btn_assign_pan.grid(row=7, column=0, pady=(2,0))
            self.draw_gear_icon(btn_assign_pan, 10, 10, 8, fill="#bbbbbb")
            btn_assign_pan.bind("<Button-1>", lambda e, c=f"pan_{i}": self.open_assign_window(c))

            # Эффект
            effect_label = tk.Label(col, text="Эффект", bg="#3c3c3c", fg="white", font=("Segoe UI", 8))
            effect_label.grid(row=8, column=0, pady=(10,0))
            effect = tk.Scale(col, from_=0, to=100, orient=tk.HORIZONTAL,
                              fg="white", bg="#3c3c3c", troughcolor="#6b6b6b",
                              highlightthickness=0, relief="flat", font=("Segoe UI", 8))
            effect.grid(row=9, column=0, sticky="ew", padx=5, pady=(0,8))
            effect.config(command=self.make_effect_callback(i))
            self.bind_save_on_release(effect)
            self.effect_scales.append(effect)

            btn_assign_effect = tk.Canvas(col, width=20, height=20, bg="#3c3c3c", highlightthickness=0)
            btn_assign_effect.grid(row=10, column=0)
            self.draw_gear_icon(btn_assign_effect, 10, 10, 8, fill="#bbbbbb")
            btn_assign_effect.bind("<Button-1>", lambda e, c=f"effect_{i}": self.open_assign_window(c))

        # Компрессор внизу
        compressor_frame = tk.Frame(self.root, bg="#2b2b2b")
        compressor_frame.grid(row=3, column=0, sticky="ew", pady=10, padx=10)
        compressor_frame.grid_columnconfigure(0, weight=1)

        self.compressor_btn = tk.Button(compressor_frame, text="Компрессор", width=20, command=self.toggle_compressor,
                                       bg="#444", fg="white", font=("Segoe UI", 10, "bold"))
        self.compressor_btn.grid(row=3, column=1, sticky="w", padx=(10,5))

        btn_assign_compressor = tk.Canvas(compressor_frame, width=20, height=20, bg="#2b2b2b", highlightthickness=0)
        btn_assign_compressor.grid(row=3, column=2)
        self.draw_gear_icon(btn_assign_compressor, 10, 10, 8, fill="#bbbbbb")
        btn_assign_compressor.bind("<Button-1>", lambda e: self.open_assign_window("compressor"))

        self.debug_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.root, text="Debug-вывод", variable=self.debug_var,
                       bg="#2b2b2b", fg="white", font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", padx=12, pady=5)

    def draw_gear_icon(self, canvas, cx, cy, r, fill="#bbb"):
        canvas.delete("all")
        canvas.create_oval(cx - r//3, cy - r//3, cx + r//3, cy + r//3, fill=fill, outline=fill)
        for angle in range(0, 360, 45):
            import math
            rad = math.radians(angle)
            x1 = cx + (r * 0.6) * math.cos(rad)
            y1 = cy + (r * 0.6) * math.sin(rad)
            x2 = cx + r * math.cos(rad)
            y2 = cy + r * math.sin(rad)
            canvas.create_line(x1, y1, x2, y2, fill=fill, width=2)

    def bind_save_on_release(self, widget):
        widget.bind("<ButtonRelease-1>", lambda e: self.save_config())

    def refresh_ports(self):
        try:
            input_ports = mido.get_input_names()
            output_ports = mido.get_output_names()
        except Exception as e:
            input_ports, output_ports = [], []
            print(f"Ошибка получения портов: {e}")

        self.in_combo['values'] = input_ports or ["— нет входов —"]
        self.out_combo['values'] = output_ports or ["— нет выходов —"]

    def set_ports_from_config(self):
        in_ports = self.in_combo['values']
        out_ports = self.out_combo['values']

        if self.in_var.get() in in_ports:
            self.in_combo.set(self.in_var.get())
        elif in_ports:
            self.in_combo.set(in_ports[0])
            self.in_var.set(in_ports[0])

        if self.out_var.get() in out_ports:
            self.out_combo.set(self.out_var.get())
        elif out_ports:
            self.out_combo.set(out_ports[0])
            self.out_var.set(out_ports[0])

    def connect_ports(self):
        if self.midi_in_port:
            self.midi_in_port.close()
        if self.midi_out_port:
            self.midi_out_port.close()

        try:
            self.midi_in_port = mido.open_input(self.in_var.get())
            self.midi_out_port = mido.open_output(self.out_var.get())
            self.status_label.config(text=f"Подключено IN: {self.in_var.get()} / OUT: {self.out_var.get()}", fg="lightgreen")
            self.poll_midi()
        except Exception as e:
            messagebox.showerror("Ошибка подключения", str(e))
            self.status_label.config(text="Ошибка MIDI", fg="red")

    def poll_midi(self):
        if not self.midi_in_port:
            return
        for msg in self.midi_in_port.iter_pending():
            if self.debug_var.get():
                print("[MIDI IN]", msg)
            self.handle_midi(msg)
        self.root.after(10, self.poll_midi)

    def open_assign_window(self, control_name):
        if self.midi_assign_mode:
            return
        self.midi_assign_mode = True
        self.current_assign_target = control_name
        self.assign_window = tk.Toplevel(self.root)
        self.assign_window.title("Назначение MIDI CC")
        self.assign_window.geometry("320x120")
        self.assign_window.configure(bg="#2b2b2b")
        self.assign_window.resizable(False, False)

        label = tk.Label(self.assign_window, text="Поверните энкодер или нажмите кнопку\nдля назначения MIDI CC",
                         font=("Segoe UI", 12), fg="white", bg="#2b2b2b", justify="center")
        label.pack(expand=True, pady=20)

        btn_cancel = tk.Button(self.assign_window, text="Отмена", command=self.cancel_assignment,
                               bg="#444", fg="white", font=("Segoe UI", 10))
        btn_cancel.pack(pady=5)

        self.assign_window.protocol("WM_DELETE_WINDOW", self.cancel_assignment)

    def cancel_assignment(self):
        self.midi_assign_mode = False
        self.current_assign_target = None
        if self.assign_window:
            self.assign_window.destroy()
            self.assign_window = None
        self.status_label.config(text="Отмена назначения MIDI CC", fg="lightgray")

    def handle_midi(self, msg):
        if msg.type != "control_change":
            return
        cc, val = msg.control, msg.value

        if self.midi_assign_mode and self.current_assign_target:
            self.assigned_controls[self.current_assign_target] = cc
            self.status_label.config(text=f"{self.current_assign_target} → CC {cc}", fg="blue")
            self.midi_assign_mode = False
            self.current_assign_target = None
            if self.assign_window:
                self.assign_window.destroy()
                self.assign_window = None
            self.save_config()
            if self.debug_var.get():
                print(f"*** Назначено {cc}")
            return

        for i in range(NUM_FADERS):
            if self.assigned_controls.get(f"fader_{i}") == cc:
                if not self.mute_states[i]:
                    self.fader_scales[i].set(min(100, max(0, int(val * 100 / 127))))
            if self.assigned_controls.get(f"pan_{i}") == cc:
                self.panorama_scales[i].set(int((val - 64) * 100 / 63))
            if self.assigned_controls.get(f"effect_{i}") == cc:
                self.effect_scales[i].set(min(100, max(0, int(val * 100 / 127))))
            if self.assigned_controls.get(f"mute_{i}") == cc:
                new_state = val >= 64
                if self.mute_states[i] != new_state:
                    self.mute_states[i] = new_state
                    self.update_mute_button(i)

        if self.assigned_controls.get("compressor") == cc:
            self.compressor_state = val >= 64
            self.update_compressor_button()

    def make_fader_callback(self, i):
        def callback(val):
            if self.mute_states[i]:
                return
            control = f"fader_{i}"
            if control in self.assigned_controls:
                cc = self.assigned_controls[control]
                midi_val = int(int(val) * 127 / 100)
                self.send_cc(cc, midi_val)
        return callback

    def make_panorama_callback(self, i):
        def callback(val):
            control = f"pan_{i}"
            if control in self.assigned_controls:
                cc = self.assigned_controls[control]
                midi_val = int((int(val) + 100) * 127 / 200)
                self.send_cc(cc, midi_val)
        return callback

    def make_effect_callback(self, i):
        def callback(val):
            control = f"effect_{i}"
            if control in self.assigned_controls:
                cc = self.assigned_controls[control]
                midi_val = int(int(val) * 127 / 100)
                self.send_cc(cc, midi_val)
        return callback

    def make_toggle_mute(self, i):
        def toggle():
            self.mute_states[i] = not self.mute_states[i]
            self.update_mute_button(i)

            control = f"mute_{i}"
            if control in self.assigned_controls:
                cc = self.assigned_controls[control]
                val = 127 if self.mute_states[i] else 0
                self.send_cc(cc, val)

            if not self.mute_states[i]:
                control_fader = f"fader_{i}"
                if control_fader in self.assigned_controls:
                    cc_fader = self.assigned_controls[control_fader]
                    val_fader = int(self.fader_scales[i].get() * 127 / 100)
                    self.send_cc(cc_fader, val_fader)

            self.save_config()
        return toggle

    def update_mute_button(self, i):
        btn = self.mute_buttons[i]
        if self.mute_states[i]:
            btn.config(text="Mute", bg="#d32f2f", fg="white", relief="sunken")
        else:
            btn.config(text="Mute", bg="#555", fg="white", relief="raised")

    def toggle_compressor(self):
        self.compressor_state = not self.compressor_state
        self.update_compressor_button()
        if "compressor" in self.assigned_controls:
            cc = self.assigned_controls["compressor"]
            val = 127 if self.compressor_state else 0
            self.send_cc(cc, val)
        self.save_config()

    def update_compressor_button(self):
        if self.compressor_state:
            self.compressor_btn.config(text="Компрессор", bg="#2e7d32")
        else:
            self.compressor_btn.config(text="Компрессор", bg="#444")

    def send_cc(self, cc, val):
        if not self.midi_out_port:
            return
        try:
            msg = mido.Message('control_change', control=cc, value=val)
            self.midi_out_port.send(msg)
            if self.debug_var.get():
                print("[MIDI OUT]", msg)
        except Exception as e:
            print(f"Ошибка отправки MIDI CC: {e}")

    def save_config(self):
        data = {
            "assigned_controls": self.assigned_controls,
            "fader_values": [s.get() for s in self.fader_scales],
            "panorama_values": [s.get() for s in self.panorama_scales],
            "effect_values": [s.get() for s in self.effect_scales],
            "mute_states": self.mute_states,
            "compressor_state": self.compressor_state,
            "midi_in_port": self.in_var.get(),
            "midi_out_port": self.out_var.get()
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения конфига: {e}")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                self.loaded_config_data = data
        except Exception as e:
            print(f"Ошибка загрузки конфига: {e}")

    def apply_loaded_values(self):
        if not self.loaded_config_data:
            return
        data = self.loaded_config_data

        self.assigned_controls = data.get("assigned_controls", {})
        fader_vals = data.get("fader_values", [])
        for i, val in enumerate(fader_vals):
            if i < len(self.fader_scales):
                self.fader_scales[i].set(val)

        pan_vals = data.get("panorama_values", [])
        for i, val in enumerate(pan_vals):
            if i < len(self.panorama_scales):
                self.panorama_scales[i].set(val)

        effect_vals = data.get("effect_values", [])
        for i, val in enumerate(effect_vals):
            if i < len(self.effect_scales):
                self.effect_scales[i].set(val)

        self.mute_states = data.get("mute_states", [False]*NUM_FADERS)
        for i in range(NUM_FADERS):
            self.update_mute_button(i)

        self.compressor_state = data.get("compressor_state", False)
        self.update_compressor_button()

        if "midi_in_port" in data:
            self.in_var.set(data["midi_in_port"])
        if "midi_out_port" in data:
            self.out_var.set(data["midi_out_port"])

    def send_all_controls_to_device(self):
        for i in range(NUM_FADERS):
            control_fader = f"fader_{i}"
            if control_fader in self.assigned_controls:
                cc = self.assigned_controls[control_fader]
                val = int(self.fader_scales[i].get() * 127 / 100)
                self.send_cc(cc, val)

            control_pan = f"pan_{i}"
            if control_pan in self.assigned_controls:
                cc = self.assigned_controls[control_pan]
                val = int((self.panorama_scales[i].get() + 100) * 127 / 200)
                self.send_cc(cc, val)

            control_effect = f"effect_{i}"
            if control_effect in self.assigned_controls:
                cc = self.assigned_controls[control_effect]
                val = int(self.effect_scales[i].get() * 127 / 100)
                self.send_cc(cc, val)

            control_mute = f"mute_{i}"
            if control_mute in self.assigned_controls:
                cc = self.assigned_controls[control_mute]
                val = 127 if self.mute_states[i] else 0
                self.send_cc(cc, val)

        if "compressor" in self.assigned_controls:
            cc = self.assigned_controls["compressor"]
            val = 127 if self.compressor_state else 0
            self.send_cc(cc, val)

def main():
    root = tk.Tk()
    app = MidiControllerApp(root)
    root.minsize(800, 600)
    root.mainloop()

if __name__ == "__main__":
    main()
