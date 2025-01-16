import sys
from pathlib import Path
import customtkinter as ctk
from utils.logger import Logger
from ui.main_window import MainWindow

def main():
    # Initialize logger first
    logger = Logger.get_instance()
    
    try:
        logger.info("=== Starting JustDownloadIt ===")
        
        # Initialize customtkinter
        logger.debug("Initializing customtkinter")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Create and run main window
        logger.info("Creating main window")
        window = MainWindow()
        logger.info("Starting main event loop")
        window.run()
        
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
        
if __name__ == "__main__":
    main()
