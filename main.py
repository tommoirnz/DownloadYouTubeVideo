# Download YouTube Video
import os
from tkinter import *
from tkinter import filedialog, messagebox
from tkinter import ttk
import yt_dlp

# Function to update the progress bar
def progress_hook(d):
    if d['status'] == 'downloading':
        # Calculate the percentage of download completed
        percent = float(d['_percent_str'].strip('%'))
        progress_bar['value'] = percent
        root.update_idletasks()

    elif d['status'] == 'finished':
        # Reset the progress bar when finished
        progress_bar['value'] = 100
        root.update_idletasks()

# Function to download the entire video with sound using yt-dlp
def download_video():
    url = url_entry.get()

    try:
        # Get the directory to save the video file
        download_path = filedialog.askdirectory()
        if not download_path:
            raise Exception("No folder selected.")

        # Get the selected video quality from the dropdown
        selected_quality = quality_var.get()

        # Define yt-dlp options to download the best video format with sound
        ydl_opts = {
            'format': f'bestvideo[height<={selected_quality}]+bestaudio/best',
            'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],  # Add progress hook
        }

        # Download the video using yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Show success message
        messagebox.showinfo("Success", f"Video has been saved at: {download_path}")

    except Exception as e:
        # Show an error message
        messagebox.showerror("Error", f"An error occurred: {e}")

# Function to create the GUI
def create_gui():
    global url_entry, quality_var, progress_bar, root

    # Create the main window
    root = Tk()
    root.title("YouTube Video Downloader")
    root.geometry("450x350")
    root.config(bg="#2E8BC0")  # Background color

    # Create and place the URL label
    Label(root, text="YouTube Video URL:", bg="#2E8BC0", fg="white", font=("Helvetica", 12)).pack(pady=10)

    # Create and place the URL entry widget
    url_entry = Entry(root, width=50, font=("Helvetica", 12), bd=2, relief="sunken")
    url_entry.pack(pady=5)

    # Create and place the quality selection label
    Label(root, text="Select Video Quality (p):", bg="#2E8BC0", fg="white", font=("Helvetica", 12)).pack(pady=10)

    # Video quality selection dropdown
    quality_var = StringVar(root)
    quality_var.set("720")  # Set default quality to 720p
    quality_options = ["144", "240", "360", "480", "720", "1080"]
    quality_menu = OptionMenu(root, quality_var, *quality_options)
    quality_menu.config(font=("Helvetica", 12), bg="#F18F01", fg="white", bd=2, relief="raised")
    quality_menu.pack(pady=10)

    # Create and place the download button
    download_button = Button(root, text="Download Video", command=download_video, bg="#F18F01", fg="white",
                             font=("Helvetica", 12, "bold"), relief="raised", bd=3)
    download_button.pack(pady=20)

    # Create a progress bar widget
    progress_bar = ttk.Progressbar(root, orient=HORIZONTAL, length=400, mode='determinate')
    progress_bar.pack(pady=20)

    # Start the Tkinter event loop
    root.mainloop()

# Run the GUI application
create_gui()
