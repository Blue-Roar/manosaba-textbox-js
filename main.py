"""主程序入口"""

from gui import ManosabaGUI
from image_loader import get_enhanced_loader

if __name__ == "__main__":
    app = ManosabaGUI()
    app.run()

    loader = get_enhanced_loader()
    loader.dll.cleanup_all()