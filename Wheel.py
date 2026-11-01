self._clear_highlight()
        self.result_hint.config(text="")
        self.spinning = True
        self._refresh_spin_button()

        count = len(self.options)
        slice_angle = 360 / count

        
        self.winning_index = random.randrange(count)
        landing = self.winning_index * slice_angle + slice_angle / 2
        landing += random.uniform(-0.38, 0.38) * slice_angle
        target = 90 - landing

        
        extra = (self.rotation - target) % 360
        self.spin_origin = self.rotation
        self.spin_delta = -(random.randint(*SPIN_TURNS) * 360 + extra)
        self.spin_duration = random.uniform(*SPIN_SECONDS)
        self.spin_start = time.perf_counter()
        self.last_tick_index = self._index_under_pointer()
        self.kick = 0.0

        self._tick()

    def _tick(self):
        if not self.spinning:
            return

        progress = (time.perf_counter() - self.spin_start) / self.spin_duration

        if progress >= 1:
            self.spin_after_id = None
            self._finish_spin()
            return

        eased = 1 - (1 - progress) ** 4  
        self.rotation = self.spin_origin + self.spin_delta * eased
        self._apply_rotation()
        self._update_pointer()

        self.spin_after_id = self.root.after(FRAME_MS, self._tick)

    def _update_pointer(self):
        index = self._index_under_pointer()

        if index != self.last_tick_index:
            self.last_tick_index = index
            self.kick = 1.0
        else:
            self.kick *= 0.8

        self.canvas.coords(self.pointer, *self._pointer_points(-24 * self.kick))

    def _finish_spin(self):
        self.rotation = (self.spin_origin + self.spin_delta) % 360
        self.kick = 0.0
        self.spinning = False

        self._apply_rotation()
        self.canvas.coords(self.pointer, *self._pointer_points(0))

        index = self.winning_index
        winner = self.options[index]

        self.spin_count += 1
        self.result_label.config(text=winner, fg=self.slice_colors[index])
        self.history.insert(0, f"{self.spin_count}.  {winner}")
        if self.history.size() > MAX_HISTORY:
            self.history.delete(MAX_HISTORY, tk.END)

        if self.remove_var.get():
            self.pending_removal = index
            self.result_hint.config(text="Will be removed on the next spin.")

        self._show_highlight(index)
        self._refresh_spin_button()

    def _show_highlight(self, index):
        self.highlight_index = index
        self._apply_rotation()
        self._pulse(6)

    def _pulse(self, toggles):
        if self.highlight_index is None:
            return

        visible = toggles % 2 == 0
        self.canvas.itemconfigure(self.highlight_item, state="normal" if visible else "hidden")

        if toggles > 0:
            self.pulse_after_id = self.root.after(170, lambda: self._pulse(toggles - 1))
        else:
            self.pulse_after_id = None

    def _clear_highlight(self):
        if self.pulse_after_id is not None:
            self.root.after_cancel(self.pulse_after_id)
            self.pulse_after_id = None

        self.highlight_index = None
        if self.highlight_item is not None:
            self.canvas.itemconfigure(self.highlight_item, state="hidden")


def main():
    
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    SpinWheelApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
