// image_loader.cpp

#include <algorithm>
#include <cstring>
#include <deque>
#include <map>
#include <memory>
#include <mutex>
#include <stack>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

#include <SDL.h>
#include <SDL_image.h>
#include <SDL_ttf.h>
#include <cJSON.h>

// Debug print
#define _DEBUG
#ifdef _DEBUG
#define DEBUG_PRINT(fmt, ...) printf("[DEBUG] " fmt "\n", ##__VA_ARGS__)
#else
#define DEBUG_PRINT(fmt, ...)
#endif

// 创建UTF-8字符串版本的括号对映射
const std::unordered_map<std::string, std::string> lt_bracket_pairs = {{"\"", "\""}, {"[", "]"}, {"<", ">"}, {"【", "】"}, {"〔", "〕"}, {"「", "」"}, {"『", "』"}, {"〖", "〗"}, {"《", "》"}, {"〈", "〉"}, {"“", "”"}};

namespace image_loader {

// Return codes
enum class LoadResult { SUCCESS = 1, FAILED = 0, FILE_NOT_FOUND = -1, SDL_INIT_FAILED = -2, IMAGE_INIT_FAILED = -3, TTF_INIT_FAILED = -4, UNSUPPORTED_FORMAT = -5, JSON_PARSE_ERROR = -6, TEXT_CONFIG_ERROR = -7 };

// Fill modes
enum class FillMode { FIT = 0, WIDTH = 1, HEIGHT = 2 };
enum class AlignMode { LEFT = 0, CENTER = 1, RIGHT = 2 };
enum class VAlignMode { TOP = 0, MIDDLE = 1, BOTTOM = 2 };

// Simple ImageData structure (compatible with original C structure)
struct ImageData {
  unsigned char *data = nullptr;
  int width = 0;
  int height = 0;
  int pitch = 0;

  ImageData() = default;

  ~ImageData() {
    if (data) {
      free(data);
      data = nullptr;
    }
  }

  // Create from SDL surface
  static std::unique_ptr<ImageData> FromSurface(SDL_Surface *surface) {
    if (!surface)
      return nullptr;

    auto image_data = std::make_unique<ImageData>();
    image_data->width = surface->w;
    image_data->height = surface->h;
    image_data->pitch = surface->pitch;

    size_t data_size = static_cast<size_t>(surface->h) * surface->pitch;
    image_data->data = static_cast<unsigned char *>(malloc(data_size));
    if (image_data->data && surface->pixels) {
      memcpy(image_data->data, surface->pixels, data_size);
    }

    return image_data;
  }

private:
  // Disable copy
  ImageData(const ImageData &) = delete;
  ImageData &operator=(const ImageData &) = delete;
};

// Font cache entry
struct FontCacheEntry {
  char font_name[256] = {0};
  int size = 0;
  TTF_Font *font = nullptr;
  FontCacheEntry *next = nullptr;

  ~FontCacheEntry() {
    if (font) {
      TTF_CloseFont(font);
      font = nullptr;
    }
    if (next) {
      delete next;
      next = nullptr;
    }
  }
};

// Static layer node
struct StaticLayerNode {
  SDL_Surface *layer_surface = nullptr;
  StaticLayerNode *next = nullptr;

  ~StaticLayerNode() {
    if (layer_surface) {
      SDL_FreeSurface(layer_surface);
      layer_surface = nullptr;
    }
    if (next) {
      delete next;
      next = nullptr;
    }
  }
};

struct StyleConfig {
  char aspect_ratio[32] = "16:9";
  unsigned char bracket_color[4] = {239, 79, 84, 255}; // #ef4f54
  char font_family[256] = "font3";
  int font_size = 55;

  // 粘贴图片设置
  char paste_align[32] = "center";
  char paste_enabled[32] = "mixed";
  char paste_fill_mode[32] = "width";
  int paste_height = 800;
  char paste_valign[32] = "middle";
  int paste_width = 800;
  int paste_x = 1500;
  int paste_y = 200;

  unsigned char shadow_color[4] = {0, 0, 0, 255}; // #000000
  int shadow_offset_x = 0;
  int shadow_offset_y = 0;
  char text_align[32] = "left";
  unsigned char text_color[4] = {255, 255, 255, 255}; // #FFFFFF
  char text_valign[32] = "top";
  int textbox_height = 245;
  int textbox_width = 1579;
  int textbox_x = 470;
  int textbox_y = 1080;
  bool use_character_color = true;
};

// ==================== 通用工具函数 ====================
namespace utils {
// 计算缩放后的尺寸
SDL_Rect CalculateScaledRect(int src_width, int src_height, int dst_width, int dst_height, const std::string &fill_mode) {
  SDL_Rect result = {0, 0, src_width, src_height};

  if (fill_mode == "width") {
    float scale = static_cast<float>(dst_width) / src_width;
    result.w = dst_width;
    result.h = static_cast<int>(src_height * scale);
  } else if (fill_mode == "height") {
    float scale = static_cast<float>(dst_height) / src_height;
    result.h = dst_height;
    result.w = static_cast<int>(src_width * scale);
  } else { // fit模式
    float scale_w = static_cast<float>(dst_width) / src_width;
    float scale_h = static_cast<float>(dst_height) / src_height;
    float scale = (scale_w < scale_h) ? scale_w : scale_h;
    result.w = static_cast<int>(src_width * scale);
    result.h = static_cast<int>(src_height * scale);
  }

  return result;
}

// 计算对齐位置
void CalculateAlignment(int region_x, int region_y, int region_width, int region_height, int item_width, int item_height, const std::string &align, const std::string &valign, int &out_x, int &out_y) {
  // 水平对齐
  if (align == "center") {
    out_x = region_x + (region_width - item_width) / 2;
  } else if (align == "right") {
    out_x = region_x + region_width - item_width;
  } else { // left
    out_x = region_x;
  }

  // 垂直对齐
  if (valign == "middle") {
    out_y = region_y + (region_height - item_height) / 2;
  } else if (valign == "bottom") {
    out_y = region_y + region_height - item_height;
  } else { // top
    out_y = region_y;
  }
}

// 根据对齐字符串计算位置
SDL_Rect CalculatePosition(const char *align_str, int offset_x, int offset_y, int target_width, int target_height, int source_width, int source_height) {
  SDL_Rect pos = {0, 0, source_width, source_height};

  if (!align_str)
    align_str = "top-left";
  std::string align(align_str);

  // 水平对齐
  if (align.find("right") != std::string::npos) {
    pos.x = target_width - source_width;
  } else if (align.find("center") != std::string::npos) {
    pos.x = (target_width - source_width) / 2;
  }

  // 垂直对齐
  if (align.find("bottom") != std::string::npos) {
    pos.y = target_height - source_height;
  } else if (align.find("middle") != std::string::npos) {
    pos.y = (target_height - source_height) / 2;
  }

  // 应用偏移
  pos.x += offset_x;
  pos.y += offset_y;

  return pos;
}

// 缩放表面
SDL_Surface *ScaleSurface(SDL_Surface *surface, float scale) {
  if (!surface || scale == 1.0f) {
    return surface;
  }

  int new_width = static_cast<int>(surface->w * scale);
  int new_height = static_cast<int>(surface->h * scale);

  SDL_Surface *scaled = SDL_CreateRGBSurfaceWithFormat(0, new_width, new_height, 32, SDL_PIXELFORMAT_ABGR8888);
  if (scaled) {
    SDL_BlitScaled(surface, nullptr, scaled, nullptr);
  }

  return scaled;
}

// 应用缩放并释放原表面
SDL_Surface *ApplyScaleAndFree(SDL_Surface *surface, float scale) {
  if (scale == 1.0f) {
    return surface;
  }

  SDL_Surface *scaled = ScaleSurface(surface, scale);
  if (scaled && scaled != surface) {
    SDL_FreeSurface(surface);
  }

  return scaled ? scaled : surface;
}

// 智能计算文本和图片区域分配
void CalculateTextImageRegions(bool has_text, bool has_image, const std::string &enabled_mode, const StyleConfig &style_config, int text_length, int emoji_count, int &text_x, int &text_y, int &text_width, int &text_height, int &image_x, int &image_y,
                               int &image_width, int &image_height) {
  // 默认使用原始区域
  text_x = style_config.textbox_x;
  text_y = style_config.textbox_y;
  text_width = style_config.textbox_width;
  text_height = style_config.textbox_height;

  image_x = style_config.paste_x;
  image_y = style_config.paste_y;
  image_width = style_config.paste_width;
  image_height = style_config.paste_height;

  // 智能区域分配逻辑
  if (has_image && has_text) {
    if (enabled_mode == "off") {
      // 估算文本长度
      int total_char_count = text_length / 3 + emoji_count;

      // 根据文本长度决定分配比例
      float image_ratio = (total_char_count < 20) ? 0.7f : 0.5f;

      // 计算分割后的区域（文本在左，图片在右）
      int total_width = style_config.textbox_width;
      int text_region_width = static_cast<int>(total_width * (1.0f - image_ratio));
      int image_region_width = total_width - text_region_width;

      // 文本区域（左侧）
      text_width = text_region_width;
      text_height = style_config.textbox_height;

      // 图片区域（右侧）
      image_x = style_config.textbox_x + text_region_width;
      image_y = style_config.textbox_y;
      image_width = image_region_width;
      image_height = style_config.textbox_height;
    }
  } else if (has_image && enabled_mode != "always") {
    // 只有图片时，使用文本框区域
    image_x = style_config.textbox_x;
    image_y = style_config.textbox_y;
    image_width = style_config.textbox_width;
    image_height = style_config.textbox_height;
  }
}

} // namespace utils

// ==================== Global Manager Class ====================
class ImageLoaderManager {
public:
  static ImageLoaderManager &GetInstance() {
    static ImageLoaderManager instance;
    return instance;
  }

  ~ImageLoaderManager() { Cleanup(); }

  // Disable copy
  ImageLoaderManager(const ImageLoaderManager &) = delete;
  ImageLoaderManager &operator=(const ImageLoaderManager &) = delete;

  // Set global configuration
  void SetGlobalConfig(const char *assets_path, float min_image_ratio) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (assets_path) {
      strncpy(assets_path_, assets_path, sizeof(assets_path_) - 1);
      assets_path_[sizeof(assets_path_) - 1] = '\0';
    }
    min_image_ratio_ = min_image_ratio;

    DEBUG_PRINT("Global configuration set: assets_path=%s", assets_path_);
  }

  // Update GUI settings
  void UpdateGuiSettings(const char *settings_json) {
    DEBUG_PRINT("Updating GUI settings");

    if (!settings_json)
      return;

    cJSON *json_root = cJSON_Parse(settings_json);
    if (!json_root) {
      DEBUG_PRINT("Failed to parse JSON");
      return;
    }

    // 解析压缩设置
    cJSON *compression = cJSON_GetObjectItem(json_root, "image_compression");
    if (compression) {
      cJSON *enabled = cJSON_GetObjectItem(compression, "pixel_reduction_enabled");
      if (enabled) {
        compression_enabled_ = cJSON_IsTrue(enabled);
      }

      cJSON *ratio = cJSON_GetObjectItem(compression, "pixel_reduction_ratio");
      if (ratio && cJSON_IsNumber(ratio)) {
        compression_ratio_ = ratio->valueint;
      }
    }

    cJSON_Delete(json_root);
  }

  void UpdateStyleConfig(const char *style_json) {
    DEBUG_PRINT("Updating style configuration");

    if (!style_json)
      return;

    cJSON *json_root = cJSON_Parse(style_json);
    if (!json_root) {
      DEBUG_PRINT("Failed to parse style JSON");
      return;
    }

    // 解析样式配置
    cJSON *aspect_ratio_item = cJSON_GetObjectItem(json_root, "aspect_ratio");
    if (aspect_ratio_item && cJSON_IsString(aspect_ratio_item)) {
      const char *aspect_ratio = aspect_ratio_item->valuestring;
      if (aspect_ratio) {
        strncpy(style_config_.aspect_ratio, aspect_ratio, sizeof(style_config_.aspect_ratio) - 1);
      }
    }

    // 解析括号颜色
    cJSON *bracket_color_item = cJSON_GetObjectItem(json_root, "bracket_color");
    if (bracket_color_item && cJSON_IsString(bracket_color_item)) {
      const char *bracket_color_str = bracket_color_item->valuestring;
      if (bracket_color_str && bracket_color_str[0] == '#') {
        int r, g, b;
        sscanf(bracket_color_str + 1, "%02x%02x%02x", &r, &g, &b);
        style_config_.bracket_color[0] = r;
        style_config_.bracket_color[1] = g;
        style_config_.bracket_color[2] = b;
        style_config_.bracket_color[3] = 255;
      }
    }

    // 解析字体
    cJSON *font_family_item = cJSON_GetObjectItem(json_root, "font_family");
    if (font_family_item && cJSON_IsString(font_family_item)) {
      const char *font_family = font_family_item->valuestring;
      if (font_family) {
        strncpy(style_config_.font_family, font_family, sizeof(style_config_.font_family) - 1);
      }
    }

    cJSON *font_size = cJSON_GetObjectItem(json_root, "font_size");
    if (font_size && cJSON_IsNumber(font_size)) {
      style_config_.font_size = font_size->valueint;
    }

    // 解析粘贴图片设置
    cJSON *paste_settings = cJSON_GetObjectItem(json_root, "paste_image_settings");
    if (paste_settings) {
      cJSON *align_item = cJSON_GetObjectItem(paste_settings, "align");
      if (align_item && cJSON_IsString(align_item)) {
        const char *align = align_item->valuestring;
        if (align)
          strncpy(style_config_.paste_align, align, sizeof(style_config_.paste_align) - 1);
      }

      cJSON *enabled_item = cJSON_GetObjectItem(paste_settings, "enabled");
      if (enabled_item && cJSON_IsString(enabled_item)) {
        const char *enabled = enabled_item->valuestring;
        if (enabled)
          strncpy(style_config_.paste_enabled, enabled, sizeof(style_config_.paste_enabled) - 1);
      }

      cJSON *fill_mode_item = cJSON_GetObjectItem(paste_settings, "fill_mode");
      if (fill_mode_item && cJSON_IsString(fill_mode_item)) {
        const char *fill_mode = fill_mode_item->valuestring;
        if (fill_mode)
          strncpy(style_config_.paste_fill_mode, fill_mode, sizeof(style_config_.paste_fill_mode) - 1);
      }

      cJSON *height = cJSON_GetObjectItem(paste_settings, "height");
      if (height && cJSON_IsNumber(height))
        style_config_.paste_height = height->valueint;

      cJSON *valign_item = cJSON_GetObjectItem(paste_settings, "valign");
      if (valign_item && cJSON_IsString(valign_item)) {
        const char *valign = valign_item->valuestring;
        if (valign)
          strncpy(style_config_.paste_valign, valign, sizeof(style_config_.paste_valign) - 1);
      }

      cJSON *width = cJSON_GetObjectItem(paste_settings, "width");
      if (width && cJSON_IsNumber(width))
        style_config_.paste_width = width->valueint;

      cJSON *x = cJSON_GetObjectItem(paste_settings, "x");
      if (x && cJSON_IsNumber(x))
        style_config_.paste_x = x->valueint;

      cJSON *y = cJSON_GetObjectItem(paste_settings, "y");
      if (y && cJSON_IsNumber(y))
        style_config_.paste_y = y->valueint;
    }

    // 解析阴影颜色
    cJSON *shadow_color_item = cJSON_GetObjectItem(json_root, "shadow_color");
    if (shadow_color_item && cJSON_IsString(shadow_color_item)) {
      const char *shadow_color_str = shadow_color_item->valuestring;
      if (shadow_color_str && shadow_color_str[0] == '#') {
        int r, g, b;
        sscanf(shadow_color_str + 1, "%02x%02x%02x", &r, &g, &b);
        style_config_.shadow_color[0] = r;
        style_config_.shadow_color[1] = g;
        style_config_.shadow_color[2] = b;
        style_config_.shadow_color[3] = 255;
      }
    }

    cJSON *shadow_offset_x = cJSON_GetObjectItem(json_root, "shadow_offset_x");
    if (shadow_offset_x && cJSON_IsNumber(shadow_offset_x)) {
      style_config_.shadow_offset_x = shadow_offset_x->valueint;
    }

    cJSON *shadow_offset_y = cJSON_GetObjectItem(json_root, "shadow_offset_y");
    if (shadow_offset_y && cJSON_IsNumber(shadow_offset_y)) {
      style_config_.shadow_offset_y = shadow_offset_y->valueint;
    }

    // 解析文本对齐
    cJSON *text_align_item = cJSON_GetObjectItem(json_root, "text_align");
    if (text_align_item && cJSON_IsString(text_align_item)) {
      const char *text_align = text_align_item->valuestring;
      if (text_align) {
        strncpy(style_config_.text_align, text_align, sizeof(style_config_.text_align) - 1);
      }
    }

    // 解析文本颜色
    cJSON *text_color_item = cJSON_GetObjectItem(json_root, "text_color");
    if (text_color_item && cJSON_IsString(text_color_item)) {
      const char *text_color_str = text_color_item->valuestring;
      if (text_color_str && text_color_str[0] == '#') {
        int r, g, b;
        sscanf(text_color_str + 1, "%02x%02x%02x", &r, &g, &b);
        style_config_.text_color[0] = r;
        style_config_.text_color[1] = g;
        style_config_.text_color[2] = b;
        style_config_.text_color[3] = 255;
      }
    }

    cJSON *text_valign_item = cJSON_GetObjectItem(json_root, "text_valign");
    if (text_valign_item && cJSON_IsString(text_valign_item)) {
      const char *text_valign = text_valign_item->valuestring;
      if (text_valign) {
        strncpy(style_config_.text_valign, text_valign, sizeof(style_config_.text_valign) - 1);
      }
    }

    // 解析文本框尺寸
    cJSON *textbox_height = cJSON_GetObjectItem(json_root, "textbox_height");
    if (textbox_height && cJSON_IsNumber(textbox_height)) {
      style_config_.textbox_height = textbox_height->valueint;
    }

    cJSON *textbox_width = cJSON_GetObjectItem(json_root, "textbox_width");
    if (textbox_width && cJSON_IsNumber(textbox_width)) {
      style_config_.textbox_width = textbox_width->valueint;
    }

    cJSON *textbox_x = cJSON_GetObjectItem(json_root, "textbox_x");
    if (textbox_x && cJSON_IsNumber(textbox_x)) {
      style_config_.textbox_x = textbox_x->valueint;
    }

    cJSON *textbox_y = cJSON_GetObjectItem(json_root, "textbox_y");
    if (textbox_y && cJSON_IsNumber(textbox_y)) {
      style_config_.textbox_y = textbox_y->valueint;
    }

    cJSON *use_character_color = cJSON_GetObjectItem(json_root, "use_character_color");
    if (use_character_color) {
      style_config_.use_character_color = cJSON_IsTrue(use_character_color);
    }

    cJSON_Delete(json_root);

    DEBUG_PRINT("Style configuration updated: font=%s, size=%d", style_config_.font_family, style_config_.font_size);
  }

  // Clear cache
  void ClearCache(const char *cache_type) {
    DEBUG_PRINT("Clearing cache: %s", cache_type ? cache_type : "null");

    std::lock_guard<std::mutex> lock(mutex_);

    if (!cache_type)
      return;

    if (strcmp(cache_type, "all") == 0) {
      ClearStaticLayerCache();
      DEBUG_PRINT("All caches cleared");
    } else if (strcmp(cache_type, "layers") == 0) {
      ClearStaticLayerCache();
      DEBUG_PRINT("Static layer cache cleared");
    }
  }

  // Initialize SDL
  bool InitSDL() {
    if (!sdl_initialized_) {
      if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        DEBUG_PRINT("SDL initialization failed: %s", SDL_GetError());
        return false;
      }
      sdl_initialized_ = true;
    }

    if (!img_initialized_) {
      int imgFlags = IMG_INIT_PNG | IMG_INIT_JPG | IMG_INIT_WEBP;
      int initted = IMG_Init(imgFlags);
      if ((initted & imgFlags) != imgFlags) {
        DEBUG_PRINT("IMG_Init warning: %s", IMG_GetError());
      }
      img_initialized_ = true;
    }

    if (!ttf_initialized_) {
      if (TTF_Init() == -1) {
        DEBUG_PRINT("TTF initialization failed: %s", TTF_GetError());
        return false;
      }
      ttf_initialized_ = true;
    }

    if (!cache_mutex_) {
      cache_mutex_ = SDL_CreateMutex();
      if (!cache_mutex_) {
        DEBUG_PRINT("Failed to create cache mutex");
        return false;
      }
    }
    if (!renderer_initialized_) {
      if (!InitRenderer()) {
        DEBUG_PRINT("Failed to initialize renderer for scaling");
        return false;
      }
    }

    return true;
  }

  // Initialize SDL Renderer (for high-quality scaling)
  bool InitRenderer() {
    if (!sdl_initialized_) {
      if (!InitSDL()) {
        return false;
      }
    }

    // 创建离屏窗口用于渲染器
    if (!renderer_window_) {
      // 创建隐藏窗口
      renderer_window_ = SDL_CreateWindow("ImageLoader Renderer", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, 1, 1, // 最小尺寸
                                          SDL_WINDOW_HIDDEN);
      if (!renderer_window_) {
        DEBUG_PRINT("Failed to create renderer window: %s", SDL_GetError());
        return false;
      }
    }

    // 创建渲染器
    if (!renderer_) {
      // 使用硬件加速渲染器，支持高质量缩放
      renderer_ = SDL_CreateRenderer(renderer_window_, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_TARGETTEXTURE);
      if (!renderer_) {
        DEBUG_PRINT("Failed to create renderer: %s", SDL_GetError());
        // 尝试软件渲染器作为备选
        renderer_ = SDL_CreateRenderer(renderer_window_, -1, SDL_RENDERER_SOFTWARE | SDL_RENDERER_TARGETTEXTURE);
        if (!renderer_) {
          DEBUG_PRINT("Failed to create software renderer: %s", SDL_GetError());
          return false;
        }
      }

      // 设置渲染器缩放质量为线性插值（更平滑）
      SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "linear");
      SDL_RenderSetLogicalSize(renderer_, 1, 1);

      DEBUG_PRINT("Renderer initialized successfully");
    }

    renderer_initialized_ = true;
    return true;
  }

  // Cleanup renderer resources
  void CleanupRenderer() {
    if (renderer_) {
      SDL_DestroyRenderer(renderer_);
      renderer_ = nullptr;
      renderer_initialized_ = false;
      DEBUG_PRINT("Renderer destroyed");
    }

    if (renderer_window_) {
      SDL_DestroyWindow(renderer_window_);
      renderer_window_ = nullptr;
      DEBUG_PRINT("Renderer window destroyed");
    }
  }

  // Generate complete image
  LoadResult GenerateCompleteImage(const char *assets_path, int canvas_width, int canvas_height, const char *components_json, const char *character_name, int emotion_index, int background_index, unsigned char **out_data, int *out_width, int *out_height) {

    DEBUG_PRINT("Starting to generate complete image");

    if (!InitSDL()) {
      return LoadResult::SDL_INIT_FAILED;
    }

    // Parse JSON
    cJSON *json_root = cJSON_Parse(components_json);
    if (!json_root) {
      DEBUG_PRINT("JSON parse error");
      return LoadResult::JSON_PARSE_ERROR;
    }

    if (!cJSON_IsArray(json_root)) {
      DEBUG_PRINT("JSON root is not an array");
      cJSON_Delete(json_root);
      return LoadResult::JSON_PARSE_ERROR;
    }

    // Create canvas
    SDL_Surface *canvas = SDL_CreateRGBSurfaceWithFormat(0, canvas_width, canvas_height, 32, SDL_PIXELFORMAT_ABGR8888);
    if (!canvas) {
      DEBUG_PRINT("Failed to create canvas: %s", SDL_GetError());
      cJSON_Delete(json_root);
      return LoadResult::FAILED;
    }

    // Fill with transparent
    SDL_FillRect(canvas, nullptr, SDL_MapRGBA(canvas->format, 0, 0, 0, 0));

    // Check for cache mark
    bool has_cache_mark = static_layer_cache_first_ != nullptr;
    int component_count = cJSON_GetArraySize(json_root);

    // Reset static layer cache pointer
    ResetStaticLayerCachePointer();

    // If no cache mark, clear and reinitialize static layer cache
    if (!has_cache_mark) {
      ClearStaticLayerCache();
      DEBUG_PRINT("Reinitializing static layer cache");
    }

    // Current static layer segment (for caching consecutive static components)
    SDL_Surface *current_static_segment = nullptr;

    // Draw each component
    for (int i = 0; i < component_count; i++) {
      cJSON *comp_obj = cJSON_GetArrayItem(json_root, i);

      // Check if it's a cache mark
      cJSON *use_cache = cJSON_GetObjectItem(comp_obj, "use_cache");
      if (use_cache && cJSON_IsTrue(use_cache)) {
        // If it's a cache mark, get next cached static layer
        SDL_Surface *cached_layer = GetNextCachedLayer();
        if (cached_layer) {
          DEBUG_PRINT("Drawing cached layer");
          SDL_BlitSurface(cached_layer, nullptr, canvas, nullptr);
        }
        continue;
      }

      bool enabled = GetJsonBool(comp_obj, "enabled", true);
      if (!enabled)
        continue;

      std::string type(GetJsonString(comp_obj, "type", ""));

      // 需要缓存图层
      if (!has_cache_mark) {
        // Determine component type
        bool use_fixed_character = GetJsonBool(comp_obj, "use_fixed_character", false);
        bool use_fixed_background = GetJsonBool(comp_obj, "use_fixed_background", false);

        // Determine if component is static
        bool is_static = false;
        if (type == "textbox" || type == "extra" || type == "namebox" || type == "text") {
          is_static = true;
        } else if (type == "character" && use_fixed_character) {
          is_static = true;
        } else if (type == "background" && use_fixed_background) {
          is_static = true;
        }

        if (is_static) {
          // If it's a static component and no current static segment, create one
          if (!current_static_segment) {
            current_static_segment = SDL_CreateRGBSurfaceWithFormat(0, canvas_width, canvas_height, 32, SDL_PIXELFORMAT_ABGR8888);
            if (current_static_segment) {
              SDL_FillRect(current_static_segment, nullptr, SDL_MapRGBA(current_static_segment->format, 0, 0, 0, 0));
              DEBUG_PRINT("Starting new static layer segment");
            }
          }
        } else if (current_static_segment) {
          // Encounter dynamic component, save current static segment
          AddStaticLayerToCache(current_static_segment);
          current_static_segment = nullptr;
          DEBUG_PRINT("Saving static layer segment");
        }
      }

      // Get draw targets
      SDL_Surface *draw_target1 = canvas; // Always draw to canvas
      SDL_Surface *draw_target2 = (!has_cache_mark && current_static_segment) ? current_static_segment : nullptr;

      // Draw component based on type
      bool draw_success = false;
      if (type == "background") {
        draw_success = DrawBackgroundComponent(draw_target1, draw_target2, comp_obj, background_index);
      } else if (type == "character") {
        draw_success = DrawCharacterComponent(draw_target1, draw_target2, comp_obj, character_name, emotion_index);
      } else if (type == "namebox") {
        draw_success = DrawNameboxComponent(draw_target1, draw_target2, comp_obj);
      } else {
        draw_success = DrawGenericComponent(draw_target1, draw_target2, comp_obj);
      }

      if (!draw_success) {
        DEBUG_PRINT("Failed to draw component: %s", type);
      }
    }

    // Handle last static segment (only when no cache mark)
    if (!has_cache_mark && current_static_segment) {
      AddStaticLayerToCache(current_static_segment);
      DEBUG_PRINT("Saving final static layer segment");
    }

    cJSON_Delete(json_root);

    // Cache the generated image as preview (replace old preview)
    ClearPreviewCache();
    preview_cache_ = ImageData::FromSurface(canvas);

    DEBUG_PRINT("Preview cache updated: %dx%d", preview_cache_->width, preview_cache_->height);

    // Return image data
    *out_width = canvas->w;
    *out_height = canvas->h;
    size_t data_size = static_cast<size_t>(canvas->h) * canvas->pitch;
    *out_data = static_cast<unsigned char *>(malloc(data_size));

    if (*out_data) {
      memcpy(*out_data, canvas->pixels, data_size);
      SDL_FreeSurface(canvas);
      DEBUG_PRINT("Image generation successful: %dx%d", *out_width, *out_height);
      return LoadResult::SUCCESS;
    } else {
      SDL_FreeSurface(canvas);
      DEBUG_PRINT("Failed to allocate output buffer");
      return LoadResult::FAILED;
    }
  }

  LoadResult DrawContentWithTextAndImage(const char *text, const char *emoji_json, unsigned char *image_data, int image_width, int image_height, int image_pitch, unsigned char **out_data, int *out_width, int *out_height) {
    DEBUG_PRINT("Starting DrawContentWithTextAndImage");
    // 1. 参数检查
    if (!text || !out_data || !out_width || !out_height) {
      DEBUG_PRINT("Invalid parameters");
      return LoadResult::FAILED;
    }

    DEBUG_PRINT("Input text length: %d", strlen(text));

    if (!InitSDL()) {
      DEBUG_PRINT("SDL initialization failed");
      return LoadResult::SDL_INIT_FAILED;
    }

    // 检查预览缓存
    SDL_LockMutex(cache_mutex_);
    bool has_preview = (preview_cache_ != nullptr);
    SDL_UnlockMutex(cache_mutex_);

    if (!has_preview) {
      DEBUG_PRINT("No preview in cache, cannot draw content");
      return LoadResult::FAILED;
    }

    // 2. 获取画布
    SDL_LockMutex(cache_mutex_);
    int canvas_width = preview_cache_->width;
    int canvas_height = preview_cache_->height;
    SDL_UnlockMutex(cache_mutex_);

    DEBUG_PRINT("Canvas size: %dx%d", canvas_width, canvas_height);

    // 创建新的画布
    SDL_Surface *canvas = SDL_CreateRGBSurfaceWithFormat(0, canvas_width, canvas_height, 32, SDL_PIXELFORMAT_ABGR8888);
    if (!canvas) {
      DEBUG_PRINT("Failed to create canvas: %s", SDL_GetError());
      return LoadResult::FAILED;
    }

    // 先绘制缓存预览作为背景
    SDL_LockMutex(cache_mutex_);
    SDL_Surface *preview_surface = SDL_CreateRGBSurfaceWithFormatFrom(preview_cache_->data, preview_cache_->width, preview_cache_->height, 32, preview_cache_->pitch, SDL_PIXELFORMAT_ABGR8888);
    SDL_UnlockMutex(cache_mutex_);

    if (preview_surface) {
      SDL_BlitSurface(preview_surface, nullptr, canvas, nullptr);
      SDL_FreeSurface(preview_surface);
      DEBUG_PRINT("Background preview drawn");
    }

    // 2. 解析emoji数据
    std::vector<std::string> emoji_list;
    std::vector<std::pair<int, int>> emoji_positions;

    if (emoji_json && emoji_json[0] != '\0') {
      DEBUG_PRINT("Parsing emoji JSON: %s", emoji_json);
      cJSON *json_root = cJSON_Parse(emoji_json);
      if (json_root) {
        cJSON *emojis_array = cJSON_GetObjectItem(json_root, "emojis");
        if (emojis_array && cJSON_IsArray(emojis_array)) {
          int array_size = cJSON_GetArraySize(emojis_array);
          for (int i = 0; i < array_size; i++) {
            cJSON *item = cJSON_GetArrayItem(emojis_array, i);
            if (item && cJSON_IsString(item)) {
              emoji_list.push_back(item->valuestring);
            }
          }
        }

        cJSON *positions_array = cJSON_GetObjectItem(json_root, "positions");
        if (positions_array && cJSON_IsArray(positions_array)) {
          int array_size = cJSON_GetArraySize(positions_array);
          for (int i = 0; i < array_size; i++) {
            cJSON *item = cJSON_GetArrayItem(positions_array, i);
            if (item && cJSON_IsArray(item)) {
              cJSON *start_item = cJSON_GetArrayItem(item, 0);
              cJSON *end_item = cJSON_GetArrayItem(item, 1);
              if (start_item && end_item && cJSON_IsNumber(start_item) && cJSON_IsNumber(end_item)) {
                emoji_positions.push_back(std::make_pair(start_item->valueint, end_item->valueint));
              }
            }
          }
        }
        cJSON_Delete(json_root);
      }
    }

    // 3. 确定文本和图片绘制区域
    bool has_text = (text && strlen(text) > 0);
    bool has_image = (image_data && image_width > 0 && image_height > 0);

    // 使用工具函数计算区域分配
    int text_x, text_y, text_width, text_height;
    int image_x, image_y, image_width_region, image_height_region;

    utils::CalculateTextImageRegions(has_text, has_image, style_config_.paste_enabled, style_config_, strlen(text), emoji_list.size(), text_x, text_y, text_width, text_height, image_x, image_y, image_width_region, image_height_region);

    // 4. 绘制图片和文本
    if (has_image) {
      DEBUG_PRINT("Drawing image: %dx%d", image_width, image_height);
      DrawImageToCanvas(canvas, image_data, image_width, image_height, image_pitch, image_x, image_y, image_width_region, image_height_region);
    }
    if (has_text) {
      DEBUG_PRINT("Drawing text: '%s'", text);
      DrawTextAndEmojiToCanvas(canvas, std::string(text), emoji_list, emoji_positions, text_x, text_y, text_width, text_height);
    }

    // 5. 压缩图像 - 使用渲染器进行高质量缩放
    if (compression_enabled_ && compression_ratio_ > 0) {
      DEBUG_PRINT("Applying compression with renderer: ratio=%d%%", compression_ratio_);

      // 计算新尺寸
      int new_width = static_cast<int>(canvas->w * (1.0f - compression_ratio_ / 100.0f));
      int new_height = static_cast<int>(canvas->h * (1.0f - compression_ratio_ / 100.0f));

      DEBUG_PRINT("Compressing from %dx%d to %dx%d", canvas->w, canvas->h, new_width, new_height);

      // 尝试使用渲染器进行高质量缩放
      SDL_Surface *compressed_surface = ScaleSurfaceWithRenderer(canvas, new_width, new_height);

      if (compressed_surface) {
        // 替换原画布
        SDL_FreeSurface(canvas);
        canvas = compressed_surface;
        DEBUG_PRINT("Renderer compression successful, new size: %dx%d", canvas->w, canvas->h);
      } else {
        // 渲染器缩放失败，回退到原始缩放方法
        DEBUG_PRINT("Renderer scaling failed, falling back to software scaling");

        // 创建压缩后的表面
        SDL_Surface *software_surface = SDL_CreateRGBSurfaceWithFormat(0, new_width, new_height, 32, SDL_PIXELFORMAT_ABGR8888);

        if (software_surface) {
          // 执行缩放
          SDL_Rect dest_rect = {0, 0, new_width, new_height};
          if (SDL_BlitScaled(canvas, nullptr, software_surface, &dest_rect) == 0) {
            // 替换原画布
            SDL_FreeSurface(canvas);
            canvas = software_surface;
            DEBUG_PRINT("Software compression successful, new size: %dx%d", canvas->w, canvas->h);
          } else {
            DEBUG_PRINT("Failed to scale surface: %s", SDL_GetError());
            SDL_FreeSurface(software_surface);
          }
        } else {
          DEBUG_PRINT("Failed to create compressed surface: %s", SDL_GetError());
        }
      }
    }

    // 6. 返回图像数据
    *out_width = canvas->w;
    *out_height = canvas->h;
    size_t data_size = static_cast<size_t>(canvas->h) * canvas->pitch;
    *out_data = static_cast<unsigned char *>(malloc(data_size));

    if (*out_data) {
      memcpy(*out_data, canvas->pixels, data_size);
      SDL_FreeSurface(canvas);
      DEBUG_PRINT("Content drawing successful: %dx%d", *out_width, *out_height);
      return LoadResult::SUCCESS;
    } else {
      SDL_FreeSurface(canvas);
      DEBUG_PRINT("Failed to allocate output buffer");
      return LoadResult::FAILED;
    }
  }

  // Cleanup all resources
  void Cleanup() {
    ClearCache("all");

    // 清理渲染器资源
    CleanupRenderer();

    if (cache_mutex_) {
      SDL_DestroyMutex(cache_mutex_);
      cache_mutex_ = nullptr;
    }

    if (ttf_initialized_) {
      TTF_Quit();
      ttf_initialized_ = false;
    }

    if (img_initialized_) {
      IMG_Quit();
      img_initialized_ = false;
    }

    if (sdl_initialized_) {
      SDL_Quit();
      sdl_initialized_ = false;
    }

    DEBUG_PRINT("All resources cleaned up");
  }

private:
  ImageLoaderManager() = default;
  StyleConfig style_config_;

  struct TextSegmentInfo {
    int start_byte; // 起始字节位置
    int end_byte;   // 结束字节位置（不包含）
    SDL_Color color;
    bool is_emoji;

    TextSegmentInfo(int s, int e, const SDL_Color &c, bool emoji = false) : start_byte(s), end_byte(e), color(c), is_emoji(emoji) {}
  };

  void ParseTextSegments(const std::string &text, const std::vector<std::string> &emoji_list, const std::vector<std::pair<int, int>> &emoji_positions, const SDL_Color &text_color, const SDL_Color &bracket_color, std::vector<TextSegmentInfo> &segments);

  // 使用分段信息进行智能换行绘制
  void DrawTextWithSegments(SDL_Surface *canvas, const std::string &text, const std::vector<TextSegmentInfo> &segments, TTF_Font *font, int emoji_size, const SDL_Rect &text_rect, AlignMode align_mode, VAlignMode valign_mode, bool has_shadow,
                            const SDL_Color &shadow_color, int shadow_offset_x, int shadow_offset_y);

  // 新增：使用emoji位置信息的文本绘制函数
  void DrawTextAndEmojiToCanvas(SDL_Surface *canvas, const std::string &text, const std::vector<std::string> &emoji_list, const std::vector<std::pair<int, int>> &emoji_positions, int text_x, int text_y, int text_width, int text_height);

  // 新增：使用渲染器进行高质量缩放
  SDL_Surface *ScaleSurfaceWithRenderer(SDL_Surface *surface, int new_width, int new_height) {
    if (!surface || new_width <= 0 || new_height <= 0) {
      DEBUG_PRINT("Invalid parameters for renderer scaling");
      return nullptr;
    }

    // 初始化渲染器（如果尚未初始化）
    if (!renderer_initialized_) {
      if (!InitRenderer()) {
        DEBUG_PRINT("Failed to initialize renderer for scaling");
        return nullptr;
      }
    }

    // 创建源纹理
    SDL_Texture *source_texture = SDL_CreateTextureFromSurface(renderer_, surface);
    if (!source_texture) {
      DEBUG_PRINT("Failed to create source texture: %s", SDL_GetError());
      return nullptr;
    }

    // 设置纹理的缩放模式为线性插值（更平滑）
    SDL_SetTextureScaleMode(source_texture, SDL_ScaleModeLinear);

    // 创建目标纹理（可渲染目标）
    SDL_Texture *target_texture = SDL_CreateTexture(renderer_, SDL_PIXELFORMAT_ABGR8888, SDL_TEXTUREACCESS_TARGET, new_width, new_height);
    if (!target_texture) {
      DEBUG_PRINT("Failed to create target texture: %s", SDL_GetError());
      SDL_DestroyTexture(source_texture);
      return nullptr;
    }

    // 设置目标纹理为当前渲染目标
    SDL_Texture *previous_target = SDL_GetRenderTarget(renderer_);
    if (SDL_SetRenderTarget(renderer_, target_texture) != 0) {
      DEBUG_PRINT("Failed to set render target: %s", SDL_GetError());
      SDL_DestroyTexture(source_texture);
      SDL_DestroyTexture(target_texture);
      return nullptr;
    }

    // 清除渲染目标（透明）
    SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 0);
    SDL_RenderClear(renderer_);

    // 将源纹理渲染到目标纹理，使用高质量缩放
    SDL_Rect dest_rect = {0, 0, new_width, new_height};
    if (SDL_RenderCopy(renderer_, source_texture, nullptr, &dest_rect) != 0) {
      DEBUG_PRINT("Failed to render copy: %s", SDL_GetError());
      SDL_SetRenderTarget(renderer_, previous_target);
      SDL_DestroyTexture(source_texture);
      SDL_DestroyTexture(target_texture);
      return nullptr;
    }

    // 恢复之前的渲染目标
    SDL_SetRenderTarget(renderer_, previous_target);

    // 创建表面来存储结果
    SDL_Surface *result_surface = SDL_CreateRGBSurfaceWithFormat(0, new_width, new_height, 32, SDL_PIXELFORMAT_ABGR8888);
    if (!result_surface) {
      DEBUG_PRINT("Failed to create result surface: %s", SDL_GetError());
      SDL_DestroyTexture(source_texture);
      SDL_DestroyTexture(target_texture);
      return nullptr;
    }

    // 从纹理读取像素到表面
    if (SDL_SetRenderTarget(renderer_, target_texture) == 0) {
      if (SDL_RenderReadPixels(renderer_, nullptr, SDL_PIXELFORMAT_ABGR8888, result_surface->pixels, result_surface->pitch) != 0) {
        DEBUG_PRINT("Failed to read pixels from texture: %s", SDL_GetError());
        SDL_FreeSurface(result_surface);
        result_surface = nullptr;
      }
      SDL_SetRenderTarget(renderer_, previous_target);
    } else {
      DEBUG_PRINT("Failed to set render target for reading pixels");
      SDL_FreeSurface(result_surface);
      result_surface = nullptr;
    }

    // 清理纹理
    SDL_DestroyTexture(source_texture);
    SDL_DestroyTexture(target_texture);

    return result_surface;
  }

  // 解析RGB颜色
  SDL_Color ParseColor(cJSON *color_item) {
    SDL_Color color = {255, 255, 255, 255};
    if (!color_item) {
      return color;
    }

    if (cJSON_IsArray(color_item)) {
      // RGB数组格式
      cJSON *r = cJSON_GetArrayItem(color_item, 0);
      cJSON *g = cJSON_GetArrayItem(color_item, 1);
      cJSON *b = cJSON_GetArrayItem(color_item, 2);
      cJSON *a = cJSON_GetArrayItem(color_item, 3);

      if (r && cJSON_IsNumber(r))
        color.r = static_cast<Uint8>(r->valueint);
      if (g && cJSON_IsNumber(g))
        color.g = static_cast<Uint8>(g->valueint);
      if (b && cJSON_IsNumber(b))
        color.b = static_cast<Uint8>(b->valueint);
      if (a && cJSON_IsNumber(a))
        color.a = static_cast<Uint8>(a->valueint);
    } else if (cJSON_IsString(color_item)) {
      // 十六进制字符串格式，如"#FFFFFF"
      const char *color_str = color_item->valuestring;
      if (color_str && color_str[0] == '#') {
        unsigned int hex_color = 0;
        if (strlen(color_str) >= 7) {
          // 解析 #RRGGBB 格式
          sscanf(color_str + 1, "%06x", &hex_color);
          color.r = (hex_color >> 16) & 0xFF;
          color.g = (hex_color >> 8) & 0xFF;
          color.b = hex_color & 0xFF;
          color.a = 255;
        } else if (strlen(color_str) >= 9) {
          // 解析 #RRGGBBAA 格式
          sscanf(color_str + 1, "%08x", &hex_color);
          color.r = (hex_color >> 24) & 0xFF;
          color.g = (hex_color >> 16) & 0xFF;
          color.b = (hex_color >> 8) & 0xFF;
          color.a = hex_color & 0xFF;
        }
      }
    }

    return color;
  }

  // 查找带扩展名的文件
  bool FindFileWithExtensions(const char *base_path, const char *extensions[], char *found_path, size_t found_path_size) {
    for (int i = 0; extensions[i]; i++) {
      snprintf(found_path, sizeof(found_path), "%s%s", base_path, extensions[i]);
      printf("Trying path: %s\n", found_path);
      SDL_RWops *file = SDL_RWFromFile(found_path, "rb");
      if (file) {
        SDL_RWclose(file);
        return true;
      }
    }
    return false;
  }

  // 加载角色图片
  SDL_Surface *LoadCharacterImage(const char *character_name, int emotion_index) {
    if (!character_name)
      return nullptr;

    // Build file path
    char file_path[1024];
    snprintf(file_path, sizeof(file_path), "%s/chara/%s/%s (%d)", assets_path_, character_name, character_name, emotion_index);

    // Try multiple extensions
    const char *extensions[] = {".webp", ".png", ".jpg", ".jpeg", ".bmp", nullptr};
    char found_path[1024] = {0};

    for (int i = 0; extensions[i]; i++) {
      snprintf(found_path, sizeof(found_path), "%s%s", file_path, extensions[i]);
      SDL_RWops *file = SDL_RWFromFile(found_path, "rb");
      if (file) {
        SDL_RWclose(file);
        break;
      }
      found_path[0] = '\0';
    }

    if (found_path[0] == '\0') {
      DEBUG_PRINT("Character image not found: %s", file_path);
      return nullptr;
    }

    // Load image
    SDL_Surface *surface = IMG_Load(found_path);
    if (!surface) {
      DEBUG_PRINT("Failed to load character: %s", found_path);
      return nullptr;
    }

    // Convert to RGBA format
    SDL_Surface *rgba_surface = SDL_ConvertSurfaceFormat(surface, SDL_PIXELFORMAT_ABGR8888, 0);
    SDL_FreeSurface(surface);

    return rgba_surface;
  }

  // 加载背景图片
  SDL_Surface *LoadBackgroundImage(const char *background_name) {
    if (!background_name)
      return nullptr;

    // Build file path
    char file_path[1024];
    snprintf(file_path, sizeof(file_path), "%s/background/%s", assets_path_, background_name);

    // Try multiple extensions
    const char *extensions[] = {".webp", ".png", ".jpg", ".jpeg", ".bmp", nullptr};
    char found_path[1024] = {0};

    for (int i = 0; extensions[i]; i++) {
      snprintf(found_path, sizeof(found_path), "%s%s", file_path, extensions[i]);
      SDL_RWops *file = SDL_RWFromFile(found_path, "rb");
      if (file) {
        SDL_RWclose(file);
        break;
      }
      found_path[0] = '\0';
    }

    // If not found in background folder, try shader folder
    if (found_path[0] == '\0') {
      snprintf(file_path, sizeof(file_path), "%s/shader/%s", assets_path_, background_name);

      for (int i = 0; extensions[i]; i++) {
        snprintf(found_path, sizeof(found_path), "%s%s", file_path, extensions[i]);
        SDL_RWops *file = SDL_RWFromFile(found_path, "rb");
        if (file) {
          SDL_RWclose(file);
          break;
        }
        found_path[0] = '\0';
      }
    }

    if (found_path[0] == '\0') {
      DEBUG_PRINT("Background image not found: %s", background_name);
      return nullptr;
    }

    // Load image
    SDL_Surface *surface = IMG_Load(found_path);
    if (!surface) {
      DEBUG_PRINT("Failed to load background: %s", found_path);
      return nullptr;
    }

    // Convert to RGBA format
    SDL_Surface *rgba_surface = SDL_ConvertSurfaceFormat(surface, SDL_PIXELFORMAT_ABGR8888, 0);
    SDL_FreeSurface(surface);

    return rgba_surface;
  }

  // 加载组件图片
  SDL_Surface *LoadComponentImage(const char *overlay) {
    if (!overlay || strlen(overlay) == 0)
      return nullptr;

    // Build component path
    char comp_path[1024];
    char base_name[256];
    strncpy(base_name, overlay, sizeof(base_name) - 1);
    base_name[sizeof(base_name) - 1] = '\0';
    char *dot = strrchr(base_name, '.');
    if (dot)
      *dot = '\0';

    char base_path[1024];
    snprintf(base_path, sizeof(base_path), "%s/shader/%s", assets_path_, base_name);

    // Try multiple extensions
    const char *extensions[] = {".webp", ".png", ".jpg", ".jpeg", ".bmp", nullptr};
    SDL_Surface *comp_surface = nullptr;

    for (int i = 0; extensions[i]; i++) {
      snprintf(comp_path, sizeof(comp_path), "%s%s", base_path, extensions[i]);
      comp_surface = IMG_Load(comp_path);
      if (comp_surface)
        break;
    }

    if (!comp_surface) {
      return nullptr;
    }

    SDL_Surface *rgba_surface = SDL_ConvertSurfaceFormat(comp_surface, SDL_PIXELFORMAT_ABGR8888, 0);
    SDL_FreeSurface(comp_surface);

    return rgba_surface;
  }

  // 背景组件绘制
  bool DrawBackgroundComponent(SDL_Surface *target1, SDL_Surface *target2, cJSON *comp_obj, int background_index) {
    const char *overlay = GetJsonString(comp_obj, "overlay", "");
    char bg_name[32];

    if (strlen(overlay) > 0) {
      char base_name[256];
      strncpy(base_name, overlay, sizeof(base_name) - 1);
      char *dot = strrchr(base_name, '.');
      if (dot)
        *dot = '\0';
      strncpy(bg_name, base_name, sizeof(bg_name));
      bg_name[sizeof(bg_name) - 1] = '\0';
    } else {
      snprintf(bg_name, sizeof(bg_name), "c%d", background_index);
    }

    SDL_Surface *bg_surface = LoadBackgroundImage(bg_name);
    if (!bg_surface)
      return false;

    // 使用工具函数应用缩放
    float scale = static_cast<float>(GetJsonNumber(comp_obj, "scale", 1.0));
    SDL_Surface *final_surface = utils::ApplyScaleAndFree(bg_surface, scale);

    // 使用工具函数计算位置
    const char *align = GetJsonString(comp_obj, "align", "top-left");
    int offset_x = static_cast<int>(GetJsonNumber(comp_obj, "offset_x", 0));
    int offset_y = static_cast<int>(GetJsonNumber(comp_obj, "offset_y", 0));

    SDL_Rect pos = utils::CalculatePosition(align, offset_x, offset_y, target1->w, target1->h, final_surface->w, final_surface->h);

    // Draw to target surfaces
    if (target1)
      SDL_BlitSurface(final_surface, nullptr, target1, &pos);
    if (target2)
      SDL_BlitSurface(final_surface, nullptr, target2, &pos);

    SDL_FreeSurface(final_surface);
    return true;
  }

  // 角色组件绘制
  bool DrawCharacterComponent(SDL_Surface *target1, SDL_Surface *target2, cJSON *comp_obj, const char *character_name, int emotion_index) {
    bool use_fixed_character = GetJsonBool(comp_obj, "use_fixed_character", false);

    const char *draw_char_name;
    int draw_emotion;

    if (use_fixed_character) {
      draw_char_name = GetJsonString(comp_obj, "character_name", "");
      draw_emotion = static_cast<int>(GetJsonNumber(comp_obj, "emotion_index", 1));
    } else {
      draw_char_name = character_name;
      draw_emotion = emotion_index;
    }

    if (!draw_char_name || strlen(draw_char_name) == 0 || draw_emotion <= 0) {
      return false;
    }

    SDL_Surface *char_surface = LoadCharacterImage(draw_char_name, draw_emotion);
    if (!char_surface)
      return false;

    // 使用工具函数应用缩放
    float comp_scale = static_cast<float>(GetJsonNumber(comp_obj, "scale", 1.0));
    float chara_scale = static_cast<float>(GetJsonNumber(comp_obj, "scale1", 1.0));
    float scale = comp_scale * chara_scale;
    SDL_Surface *final_surface = utils::ApplyScaleAndFree(char_surface, scale);

    // 使用工具函数计算位置
    const char *align = GetJsonString(comp_obj, "align", "top-left");
    int comp_offset_x = static_cast<int>(GetJsonNumber(comp_obj, "offset_x", 0));
    int comp_offset_y = static_cast<int>(GetJsonNumber(comp_obj, "offset_y", 0));
    int chara_offset_x = static_cast<int>(GetJsonNumber(comp_obj, "offset_x1", 0));
    int chara_offset_y = static_cast<int>(GetJsonNumber(comp_obj, "offset_y1", 0));
    int offset_x = comp_offset_x + chara_offset_x;
    int offset_y = comp_offset_y + chara_offset_y;

    SDL_Rect pos = utils::CalculatePosition(align, offset_x, offset_y, target1->w, target1->h, final_surface->w, final_surface->h);

    SDL_Surface *temp_layer = SDL_CreateRGBSurfaceWithFormat(0, target1->w, target1->h, 32, SDL_PIXELFORMAT_ABGR8888);

    SDL_BlitSurface(final_surface, nullptr, temp_layer, &pos);
    SDL_FreeSurface(final_surface);
    final_surface = temp_layer;

    // Draw to target surfaces
    if (target1)
      SDL_BlitSurface(final_surface, nullptr, target1, nullptr);
    if (target2)
      SDL_BlitSurface(final_surface, nullptr, target2, nullptr);

    SDL_FreeSurface(final_surface);
    return true;
  }

  SDL_Surface *DrawNameboxWithText(cJSON *comp_obj) {
    const char *overlay = GetJsonString(comp_obj, "overlay", "");
    // DEBUG_PRINT("draw_namebox_with_text: overlay = %s", overlay);

    if (strlen(overlay) == 0) {
      DEBUG_PRINT("draw_namebox_with_text: Empty overlay");
      return nullptr;
    }

    // 加载图像
    SDL_Surface *namebox_surface = LoadComponentImage(overlay);
    if (!namebox_surface) {
      DEBUG_PRINT("draw_namebox_with_text: Failed to load namebox image: %s", overlay);
      return nullptr;
    }

    // DEBUG_PRINT("draw_namebox_with_text: Namebox loaded, size: %dx%d", namebox_surface->w, namebox_surface->h);

    // 获取文本配置
    cJSON *textcfg_obj = cJSON_GetObjectItem(comp_obj, "textcfg");
    if (!textcfg_obj || !cJSON_IsArray(textcfg_obj)) {
      DEBUG_PRINT("draw_namebox_with_text: No text configurations found for namebox");
      return namebox_surface; // 返回没有文字的namebox
    }

    int text_config_count = cJSON_GetArraySize(textcfg_obj);
    // DEBUG_PRINT("draw_namebox_with_text: Found %d text configurations", text_config_count);

    if (text_config_count == 0) {
      DEBUG_PRINT("draw_namebox_with_text: Empty text configurations for namebox");
      return namebox_surface;
    }

    // 查找最大字体大小用于基线计算
    int max_font_size = 0;
    for (int i = 0; i < text_config_count; i++) {
      cJSON *config_obj = cJSON_GetArrayItem(textcfg_obj, i);
      if (config_obj) {
        int font_size = static_cast<int>(GetJsonNumber(config_obj, "font_size", 92.0));
        // DEBUG_PRINT("draw_namebox_with_text: Config %d, font_size = %d", i, font_size);
        if (font_size > max_font_size) {
          max_font_size = font_size;
        }
      }
    }

    if (max_font_size == 0) {
      max_font_size = 92; // 默认值
    }
    // DEBUG_PRINT("draw_namebox_with_text: Max font size = %d", max_font_size);

    // 计算基线位置（基于最大字体大小）- 高度的65%
    int baseline_y = static_cast<int>(namebox_surface->h * 0.65);
    // DEBUG_PRINT("draw_namebox_with_text: baseline_y = %d (namebox height = %d)", baseline_y, namebox_surface->h);

    // 起始X位置 - 以270为中心，根据最大字体大小调整
    int current_x = 270 - max_font_size / 2;
    // DEBUG_PRINT("draw_namebox_with_text: Starting current_x = %d", current_x);

    // 获取字体名称
    const char *font_name = GetJsonString(comp_obj, "font_name", "font3");
    // DEBUG_PRINT("draw_namebox_with_text: font_name = %s", font_name);

    // 绘制每个文本
    for (int i = 0; i < text_config_count; i++) {
      cJSON *config_obj = cJSON_GetArrayItem(textcfg_obj, i);
      if (!config_obj) {
        continue;
      }

      const char *text = GetJsonString(config_obj, "text", "");
      if (strlen(text) == 0) {
        // DEBUG_PRINT("draw_namebox_with_text: Config %d has empty text", i);
        continue;
      }

      int font_size = static_cast<int>(GetJsonNumber(config_obj, "font_size", 92.0));
      //   DEBUG_PRINT("draw_namebox_with_text: Drawing text: '%s', font_size = %d", text, font_size);

      // 获取字体颜色
      SDL_Color text_color;
      cJSON *color_obj = cJSON_GetObjectItem(config_obj, "font_color");
      if (color_obj) {
        text_color = ParseColor(color_obj);
        // DEBUG_PRINT("draw_namebox_with_text: Color RGB(%d, %d, %d)", text_color.r, text_color.g, text_color.b);
      } else {
        text_color = {255, 255, 255, 255}; // 默认白色
        // DEBUG_PRINT("draw_namebox_with_text: Using default color");
      }

      // 获取字体
      TTF_Font *font = GetFontCached(font_name, font_size);
      if (!font) {
        DEBUG_PRINT("draw_namebox_with_text: Failed to get font: %s (size %d)", font_name, font_size);
        continue;
      }

      // 阴影颜色（黑色）
      SDL_Color shadow_color = {0, 0, 0, 255};

      // 计算文本的度量信息，用于基线对齐
      int text_width, text_height;
      TTF_SizeUTF8(font, text, &text_width, &text_height);

      // 获取字体的ascent（基线以上的高度）
      int ascent = TTF_FontAscent(font);
      //   DEBUG_PRINT("draw_namebox_with_text: Text size: %dx%d, ascent: %d", text_width, text_height, ascent);

      // 基线对齐：baseline_y - ascent 得到文本顶部的y坐标
      int text_top_y = baseline_y - ascent;

      // 绘制阴影文字 (2像素偏移)
      SDL_Surface *shadow_surface = TTF_RenderUTF8_Blended(font, text, shadow_color);
      if (shadow_surface) {
        int shadow_x = current_x + 2;
        int shadow_y = text_top_y + 2;

        // DEBUG_PRINT("draw_namebox_with_text: Drawing shadow at (%d, %d)", shadow_x, shadow_y);

        SDL_Rect shadow_rect = {shadow_x, shadow_y, shadow_surface->w, shadow_surface->h};
        SDL_BlitSurface(shadow_surface, nullptr, namebox_surface, &shadow_rect);
        SDL_FreeSurface(shadow_surface);
      }

      // 绘制主文字
      SDL_Surface *text_surface = TTF_RenderUTF8_Blended(font, text, text_color);
      if (!text_surface) {
        DEBUG_PRINT("draw_namebox_with_text: Failed to render text: %s", text);
        continue;
      }

      int main_x = current_x;
      int main_y = text_top_y;

      //   DEBUG_PRINT("draw_namebox_with_text: Drawing main text at (%d, %d)", main_x, main_y);

      SDL_Rect main_rect = {main_x, main_y, text_surface->w, text_surface->h};
      SDL_BlitSurface(text_surface, nullptr, namebox_surface, &main_rect);

      // 更新当前X位置为下一个文本
      current_x += text_width;
      DEBUG_PRINT("draw_namebox_with_text: Updated current_x = %d", current_x);

      SDL_FreeSurface(text_surface);
    }

    DEBUG_PRINT("draw_namebox_with_text: Completed successfully");
    return namebox_surface;
  }

  // 名字框组件绘制
  bool DrawNameboxComponent(SDL_Surface *target1, SDL_Surface *target2, cJSON *comp_obj) {
    // DEBUG_PRINT("DrawNameboxComponent: Starting...");

    // 使用新的函数绘制带文字的namebox
    SDL_Surface *namebox_surface = DrawNameboxWithText(comp_obj);
    // 加载图像
    if (!namebox_surface) {
      //   DEBUG_PRINT("DrawNameboxComponent: Failed to draw namebox with text");
      return false;
    }

    // 使用工具函数应用缩放
    float scale = static_cast<float>(GetJsonNumber(comp_obj, "scale", 1.0));
    SDL_Surface *final_surface = utils::ApplyScaleAndFree(namebox_surface, scale);

    // 使用工具函数计算位置
    const char *align = GetJsonString(comp_obj, "align", "top-left");
    int offset_x = static_cast<int>(GetJsonNumber(comp_obj, "offset_x", 0));
    int offset_y = static_cast<int>(GetJsonNumber(comp_obj, "offset_y", 0));

    SDL_Rect pos = utils::CalculatePosition(align, offset_x, offset_y, target1->w, target1->h, final_surface->w, final_surface->h);

    SDL_Surface *temp_layer = SDL_CreateRGBSurfaceWithFormat(0, target1->w, target1->h, 32, SDL_PIXELFORMAT_ABGR8888);

    SDL_BlitSurface(final_surface, nullptr, temp_layer, &pos);
    SDL_FreeSurface(final_surface);
    final_surface = temp_layer;

    // 绘制到目标表面
    if (target1)
      SDL_BlitSurface(final_surface, nullptr, target1, nullptr);
    if (target2)
      SDL_BlitSurface(final_surface, nullptr, target2, nullptr);

    SDL_FreeSurface(final_surface);

    // DEBUG_PRINT("DrawNameboxComponent: Completed successfully");
    return true;
  }

  // 图层组件绘制
  bool DrawGenericComponent(SDL_Surface *target1, SDL_Surface *target2, cJSON *comp_obj) {
    const char *overlay = GetJsonString(comp_obj, "overlay", "");
    const char *type = GetJsonString(comp_obj, "type", "");

    // 处理文本组件
    if (strcmp(type, "text") == 0) {
      return DrawTextComponent(target1, target2, comp_obj);
    }

    // 原有的图层组件处理
    if (strlen(overlay) == 0)
      return true;

    SDL_Surface *comp_surface = LoadComponentImage(overlay);
    if (!comp_surface)
      return false;

    // 使用工具函数应用缩放
    float scale = static_cast<float>(GetJsonNumber(comp_obj, "scale", 1.0));
    SDL_Surface *final_surface = utils::ApplyScaleAndFree(comp_surface, scale);

    // 使用工具函数计算位置
    const char *align = GetJsonString(comp_obj, "align", "top-left");
    int offset_x = static_cast<int>(GetJsonNumber(comp_obj, "offset_x", 0));
    int offset_y = static_cast<int>(GetJsonNumber(comp_obj, "offset_y", 0));

    SDL_Rect pos = utils::CalculatePosition(align, offset_x, offset_y, target1->w, target1->h, final_surface->w, final_surface->h);

    // Draw to target surfaces
    if (target1)
      SDL_BlitSurface(final_surface, nullptr, target1, &pos);
    if (target2)
      SDL_BlitSurface(final_surface, nullptr, target2, &pos);

    SDL_FreeSurface(final_surface);
    return true;
  }

  bool DrawTextComponent(SDL_Surface *target1, SDL_Surface *target2, cJSON *comp_obj) {
    const char *text = GetJsonString(comp_obj, "text", "");
    if (strlen(text) == 0) {
      DEBUG_PRINT("DrawTextComponent: Empty text");
      return true;
    }

    // 获取字体配置
    const char *font_name = GetJsonString(comp_obj, "font_family", style_config_.font_family);
    int font_size = static_cast<int>(GetJsonNumber(comp_obj, "font_size", style_config_.font_size));

    DEBUG_PRINT("DrawTextComponent: text='%s', font=%s, size=%d", text, font_name, font_size);

    // 获取颜色配置 - 支持多种格式
    SDL_Color text_color = {255, 255, 255, 255};
    cJSON *text_color_obj = cJSON_GetObjectItem(comp_obj, "text_color");
    if (text_color_obj) {
      text_color = ParseColor(text_color_obj);
    } else {
      // 如果没有指定文本颜色，使用样式配置的默认颜色
      text_color.r = style_config_.text_color[0];
      text_color.g = style_config_.text_color[1];
      text_color.b = style_config_.text_color[2];
      text_color.a = style_config_.text_color[3];
    }

    DEBUG_PRINT("DrawTextComponent: text_color=(%d,%d,%d,%d)", text_color.r, text_color.g, text_color.b, text_color.a);

    SDL_Color shadow_color = {0, 0, 0, 255};
    cJSON *shadow_color_obj = cJSON_GetObjectItem(comp_obj, "shadow_color");
    if (shadow_color_obj) {
      shadow_color = ParseColor(shadow_color_obj);
    } else {
      // 如果没有指定阴影颜色，使用样式配置的默认颜色
      shadow_color.r = style_config_.shadow_color[0];
      shadow_color.g = style_config_.shadow_color[1];
      shadow_color.b = style_config_.shadow_color[2];
      shadow_color.a = style_config_.shadow_color[3];
    }

    int shadow_offset_x = static_cast<int>(GetJsonNumber(comp_obj, "shadow_offset_x", style_config_.shadow_offset_x));
    int shadow_offset_y = static_cast<int>(GetJsonNumber(comp_obj, "shadow_offset_y", style_config_.shadow_offset_y));

    // 获取对齐方式
    const char *align_str = GetJsonString(comp_obj, "align", "top-left");
    int offset_x = static_cast<int>(GetJsonNumber(comp_obj, "offset_x", 0));
    int offset_y = static_cast<int>(GetJsonNumber(comp_obj, "offset_y", 0));

    // 获取最大宽度（用于换行）
    int max_width = static_cast<int>(GetJsonNumber(comp_obj, "max_width", 0));

    // 获取字体
    TTF_Font *font = GetFontCached(font_name, font_size);
    if (!font) {
      DEBUG_PRINT("DrawTextComponent: Failed to get font: %s (size %d)", font_name, font_size);
      return false;
    }

    // 计算文本尺寸
    int text_width, text_height;
    SDL_Surface *final_text_surface = nullptr;

    if (max_width > 0) {
      // 有最大宽度，需要换行
      DEBUG_PRINT("DrawTextComponent: Max width: %d, creating multi-line text", max_width);

      // 简单的换行逻辑
      std::vector<std::string> lines;
      std::string current_line;
      std::string utf8_text = text;

      // 按字符分割
      for (size_t i = 0; i < utf8_text.size();) {
        unsigned char c = static_cast<unsigned char>(utf8_text[i]);
        int char_len = 1;

        if (c < 0x80)
          char_len = 1;
        else if ((c & 0xE0) == 0xC0)
          char_len = 2;
        else if ((c & 0xF0) == 0xE0)
          char_len = 3;
        else if ((c & 0xF8) == 0xF0)
          char_len = 4;

        if (i + char_len <= utf8_text.size()) {
          std::string current_char = utf8_text.substr(i, char_len);

          // 检查加上这个字符后是否超过最大宽度
          std::string test_line = current_line + current_char;
          int test_width;
          TTF_SizeUTF8(font, test_line.c_str(), &test_width, nullptr);

          if (test_width > max_width && !current_line.empty()) {
            // 需要换行
            lines.push_back(current_line);
            current_line = current_char;
          } else {
            current_line += current_char;
          }

          i += char_len;
        } else {
          i++; // 跳过无效字符
        }
      }

      if (!current_line.empty()) {
        lines.push_back(current_line);
      }

      // 计算总高度
      int line_height = TTF_FontHeight(font);
      int line_spacing = static_cast<int>(line_height * 0.15); // 15%行间距
      text_height = lines.size() * line_height + (lines.size() - 1) * line_spacing;
      text_width = max_width;

      DEBUG_PRINT("DrawTextComponent: %zu lines, total height: %d", lines.size(), text_height);

      // 创建文本表面
      final_text_surface = SDL_CreateRGBSurfaceWithFormat(0, text_width, text_height, 32, SDL_PIXELFORMAT_ABGR8888);
      if (!final_text_surface) {
        DEBUG_PRINT("DrawTextComponent: Failed to create text surface");
        return false;
      }

      // 填充透明背景
      SDL_FillRect(final_text_surface, nullptr, SDL_MapRGBA(final_text_surface->format, 0, 0, 0, 0));

      // 绘制每一行
      int current_y = 0;
      for (const auto &line : lines) {
        if (line.empty())
          continue;

        int line_width, single_line_height;
        TTF_SizeUTF8(font, line.c_str(), &line_width, &single_line_height);

        // 在最大宽度内水平对齐（默认左对齐）
        int line_x = 0;

        // 绘制阴影
        if (shadow_offset_x != 0 || shadow_offset_y != 0) {
          SDL_Surface *shadow_surface = TTF_RenderUTF8_Blended(font, line.c_str(), shadow_color);
          if (shadow_surface) {
            SDL_Rect shadow_rect = {line_x + shadow_offset_x, current_y + shadow_offset_y, shadow_surface->w, shadow_surface->h};
            SDL_BlitSurface(shadow_surface, nullptr, final_text_surface, &shadow_rect);
            SDL_FreeSurface(shadow_surface);
          }
        }

        // 绘制文本
        SDL_Surface *line_surface = TTF_RenderUTF8_Blended(font, line.c_str(), text_color);
        if (line_surface) {
          SDL_Rect line_rect = {line_x, current_y, line_surface->w, line_surface->h};
          SDL_BlitSurface(line_surface, nullptr, final_text_surface, &line_rect);
          SDL_FreeSurface(line_surface);
        }

        current_y += line_height + line_spacing;
      }
    } else {
      // 没有最大宽度，单行绘制
      TTF_SizeUTF8(font, text, &text_width, &text_height);

      DEBUG_PRINT("DrawTextComponent: Single line, size: %dx%d", text_width, text_height);

      // 创建文本表面（包含阴影）
      int total_width = text_width + abs(shadow_offset_x);
      int total_height = text_height + abs(shadow_offset_y);

      final_text_surface = SDL_CreateRGBSurfaceWithFormat(0, total_width, total_height, 32, SDL_PIXELFORMAT_ABGR8888);
      if (!final_text_surface) {
        DEBUG_PRINT("DrawTextComponent: Failed to create text surface");
        return false;
      }

      // 填充透明背景
      SDL_FillRect(final_text_surface, nullptr, SDL_MapRGBA(final_text_surface->format, 0, 0, 0, 0));

      // 计算阴影和文本的偏移
      int shadow_x = (shadow_offset_x < 0) ? 0 : shadow_offset_x;
      int shadow_y = (shadow_offset_y < 0) ? 0 : shadow_offset_y;
      int text_x = (shadow_offset_x > 0) ? 0 : -shadow_offset_x;
      int text_y = (shadow_offset_y > 0) ? 0 : -shadow_offset_y;

      // 绘制阴影
      if (shadow_offset_x != 0 || shadow_offset_y != 0) {
        SDL_Surface *shadow_surface = TTF_RenderUTF8_Blended(font, text, shadow_color);
        if (shadow_surface) {
          SDL_Rect shadow_rect = {shadow_x, shadow_y, shadow_surface->w, shadow_surface->h};
          SDL_BlitSurface(shadow_surface, nullptr, final_text_surface, &shadow_rect);
          SDL_FreeSurface(shadow_surface);
        }
      }

      // 绘制文本
      SDL_Surface *text_surface = TTF_RenderUTF8_Blended(font, text, text_color);
      if (text_surface) {
        SDL_Rect text_rect = {text_x, text_y, text_surface->w, text_surface->h};
        SDL_BlitSurface(text_surface, nullptr, final_text_surface, &text_rect);
        SDL_FreeSurface(text_surface);
      }
    }

    if (!final_text_surface) {
      DEBUG_PRINT("DrawTextComponent: No text surface created");
      return false;
    }

    // 使用工具函数计算位置
    SDL_Rect pos = utils::CalculatePosition(align_str, offset_x, offset_y, target1->w, target1->h, final_text_surface->w, final_text_surface->h);

    DEBUG_PRINT("DrawTextComponent: Drawing at position (%d, %d), size: %dx%d", pos.x, pos.y, pos.w, pos.h);

    // 绘制到目标表面
    if (target1) {
      SDL_BlitSurface(final_text_surface, nullptr, target1, &pos);
      DEBUG_PRINT("DrawTextComponent: Drawn to target1");
    }
    if (target2) {
      SDL_BlitSurface(final_text_surface, nullptr, target2, &pos);
      DEBUG_PRINT("DrawTextComponent: Drawn to target2");
    }

    SDL_FreeSurface(final_text_surface);

    DEBUG_PRINT("DrawTextComponent: Completed successfully");
    return true;
  }

  // Get font (with caching)
  TTF_Font *GetFontCached(const char *font_name, int size) {
    if (!ttf_initialized_)
      return nullptr;

    SDL_LockMutex(cache_mutex_);

    // Search in cache
    FontCacheEntry *current = font_cache_;
    while (current) {
      if (strcmp(current->font_name, font_name) == 0 && current->size == size) {
        SDL_UnlockMutex(cache_mutex_);
        return current->font;
      }
      current = current->next;
    }

    // Build font path
    char font_path[1024];
    const char *extensions[] = {".ttf", ".otf", ".ttc", nullptr};
    TTF_Font *font = nullptr;

    for (int i = 0; extensions[i]; i++) {
      snprintf(font_path, sizeof(font_path), "%s/fonts/%s%s", assets_path_, font_name, extensions[i]);

      SDL_RWops *file = SDL_RWFromFile(font_path, "rb");
      if (file) {
        SDL_RWclose(file);
        font = TTF_OpenFont(font_path, size);
        if (font) {
          // Add to cache
          FontCacheEntry *new_entry = new FontCacheEntry();
          strncpy(new_entry->font_name, font_name, sizeof(new_entry->font_name));
          new_entry->size = size;
          new_entry->font = font;
          new_entry->next = font_cache_;
          font_cache_ = new_entry;

          SDL_UnlockMutex(cache_mutex_);
          return font;
        }
      }
    }

    SDL_UnlockMutex(cache_mutex_);
    DEBUG_PRINT("Font not found: %s", font_name);
    return nullptr;
  }

  // 绘制图片到画布
  void DrawImageToCanvas(SDL_Surface *canvas, unsigned char *image_data, int image_width, int image_height, int image_pitch, int paste_x, int paste_y, int paste_width, int paste_height) {
    StyleConfig *config = &style_config_;

    DEBUG_PRINT("Drawing image to region: %dx%d at (%d,%d)", paste_width, paste_height, paste_x, paste_y);
    DEBUG_PRINT("Input image size: %dx%d", image_width, image_height);

    SDL_Surface *img_surface = SDL_CreateRGBSurfaceWithFormatFrom(image_data, image_width, image_height, 32, image_pitch, SDL_PIXELFORMAT_ABGR8888);

    if (!img_surface) {
      DEBUG_PRINT("Failed to create image surface");
      return;
    }

    // 使用工具函数计算缩放后的尺寸
    SDL_Rect scaled_rect = utils::CalculateScaledRect(img_surface->w, img_surface->h, paste_width, paste_height, config->paste_fill_mode);

    DEBUG_PRINT("Fill mode: %s, new size: %dx%d", config->paste_fill_mode, scaled_rect.w, scaled_rect.h);

    // 调整图片大小 - 使用渲染器进行高质量缩放
    SDL_Surface *resized_surface = nullptr;

    // 尝试使用渲染器进行高质量缩放
    if (renderer_initialized_) {
      resized_surface = ScaleSurfaceWithRenderer(img_surface, scaled_rect.w, scaled_rect.h);
    }

    // 如果渲染器缩放失败，回退到原始方法
    if (!resized_surface) {
      DEBUG_PRINT("Renderer scaling failed, falling back to software scaling");
      resized_surface = SDL_CreateRGBSurfaceWithFormat(0, scaled_rect.w, scaled_rect.h, 32, SDL_PIXELFORMAT_ABGR8888);

      if (resized_surface) {
        SDL_BlitScaled(img_surface, nullptr, resized_surface, nullptr);
      }
    }

    if (resized_surface) {
      // 使用工具函数计算对齐位置
      int final_x, final_y;
      utils::CalculateAlignment(paste_x, paste_y, paste_width, paste_height, scaled_rect.w, scaled_rect.h, config->paste_align, config->paste_valign, final_x, final_y);

      SDL_Rect dest_rect = {final_x, final_y, scaled_rect.w, scaled_rect.h};
      DEBUG_PRINT("Drawing image to canvas at (%d, %d) with size %dx%d", dest_rect.x, dest_rect.y, dest_rect.w, dest_rect.h);

      SDL_BlitSurface(resized_surface, nullptr, canvas, &dest_rect);
      SDL_FreeSurface(resized_surface);
    } else {
      DEBUG_PRINT("Failed to create resized surface");
    }

    SDL_FreeSurface(img_surface);
    DEBUG_PRINT("Image drawing completed");
  }

  // Cache management functions
  void ClearPreviewCache() {
    SDL_LockMutex(cache_mutex_);
    preview_cache_.reset();
    SDL_UnlockMutex(cache_mutex_);
  }

  void ClearStaticLayerCache() {
    SDL_LockMutex(cache_mutex_);
    if (static_layer_cache_first_) {
      delete static_layer_cache_first_;
      static_layer_cache_first_ = nullptr;
      static_layer_cache_current_ = nullptr;
      static_layer_cache_count_ = 0;
    }
    SDL_UnlockMutex(cache_mutex_);
  }

  void AddStaticLayerToCache(SDL_Surface *layer_surface) {
    if (!layer_surface)
      return;

    SDL_LockMutex(cache_mutex_);

    StaticLayerNode *new_node = new StaticLayerNode();
    new_node->layer_surface = layer_surface;
    new_node->next = nullptr;

    if (!static_layer_cache_first_) {
      static_layer_cache_first_ = new_node;
      static_layer_cache_current_ = new_node;
    } else {
      // Find the last node
      StaticLayerNode *last = static_layer_cache_first_;
      while (last->next) {
        last = last->next;
      }
      last->next = new_node;
    }

    static_layer_cache_count_++;

    SDL_UnlockMutex(cache_mutex_);

    DEBUG_PRINT("Added layer to cache, current count: %d", static_layer_cache_count_);
  }

  SDL_Surface *GetNextCachedLayer() {
    SDL_LockMutex(cache_mutex_);

    if (!static_layer_cache_current_) {
      SDL_UnlockMutex(cache_mutex_);
      return nullptr;
    }

    SDL_Surface *layer = static_layer_cache_current_->layer_surface;
    static_layer_cache_current_ = static_layer_cache_current_->next;

    SDL_UnlockMutex(cache_mutex_);

    DEBUG_PRINT("Retrieved cached layer");
    return layer;
  }

  void ResetStaticLayerCachePointer() {
    SDL_LockMutex(cache_mutex_);
    static_layer_cache_current_ = static_layer_cache_first_;
    SDL_UnlockMutex(cache_mutex_);
  }

  // JSON helper functions
  static const char *GetJsonString(cJSON *obj, const char *key, const char *default_val) {
    cJSON *item = cJSON_GetObjectItem(obj, key);
    if (item && cJSON_IsString(item)) {
      return item->valuestring;
    }
    return default_val;
  }

  static double GetJsonNumber(cJSON *obj, const char *key, double default_val) {
    cJSON *item = cJSON_GetObjectItem(obj, key);
    if (item && cJSON_IsNumber(item)) {
      return item->valuedouble;
    }
    return default_val;
  }

  static bool GetJsonBool(cJSON *obj, const char *key, bool default_val) {
    cJSON *item = cJSON_GetObjectItem(obj, key);
    if (item) {
      if (cJSON_IsBool(item)) {
        return cJSON_IsTrue(item);
      } else if (cJSON_IsNumber(item)) {
        return item->valueint != 0;
      }
    }
    return default_val;
  }

private:
  // Global configuration
  char assets_path_[1024] = {0};
  float min_image_ratio_ = 0.2f;

  // SDL state
  bool sdl_initialized_ = false;
  bool img_initialized_ = false;
  bool ttf_initialized_ = false;

  // Renderer state
  SDL_Window *renderer_window_ = nullptr;
  SDL_Renderer *renderer_ = nullptr;
  bool renderer_initialized_ = false;

  // 压缩设置
  bool compression_enabled_ = false;
  int compression_ratio_ = 40; // 默认40%

  // Caches (only fonts, static layers, and preview)
  FontCacheEntry *font_cache_ = nullptr;
  std::unique_ptr<ImageData> preview_cache_;

  StaticLayerNode *static_layer_cache_first_ = nullptr;
  StaticLayerNode *static_layer_cache_current_ = nullptr;
  int static_layer_cache_count_ = 0;

  SDL_mutex *cache_mutex_ = nullptr;

  std::mutex mutex_;

  // 新增：加载emoji图片
  SDL_Surface *LoadEmojiImage(const std::string &emoji_text, int target_size);
  //   void DrawImageToCanvasWithRegion(SDL_Surface *canvas, unsigned char *image_data, int image_width, int image_height, int image_pitch, int region_x, int region_y, int region_width, int region_height);
  // 新增：将emoji字符串转换为文件名
  std::string EmojiToFileName(const std::string &emoji_text);
};

// ==================== 新增函数实现 ====================

// 实现ParseTextSegments函数
void ImageLoaderManager::ParseTextSegments(const std::string &text, const std::vector<std::string> &emoji_list, const std::vector<std::pair<int, int>> &emoji_positions, const SDL_Color &text_color, const SDL_Color &bracket_color,
                                           std::vector<TextSegmentInfo> &segments) {
  DEBUG_PRINT("=== ParseTextSegments ===");
  DEBUG_PRINT("Text length: %zu bytes", text.size());

  if (emoji_positions.empty()) {
    // 没有emoji，直接解析括号
    std::stack<std::pair<int, SDL_Color>> bracket_stack; // 存储位置和颜色
    int i = 0;

    while (i < text.size()) {
      unsigned char c = static_cast<unsigned char>(text[i]);
      int char_len = 1;

      if (c < 0x80)
        char_len = 1;
      else if ((c & 0xE0) == 0xC0)
        char_len = 2;
      else if ((c & 0xF0) == 0xE0)
        char_len = 3;
      else if ((c & 0xF8) == 0xF0)
        char_len = 4;

      std::string current_char;
      if (i + char_len <= text.size()) {
        current_char = text.substr(i, char_len);
      } else {
        current_char = text.substr(i, 1);
        char_len = 1;
      }

      // 检查是否是左括号
      auto it_left = lt_bracket_pairs.find(current_char);
      if (it_left != lt_bracket_pairs.end() && bracket_stack.empty()) {
        // 开始一个括号段
        bracket_stack.push({i, bracket_color});
        i += char_len;
        continue;
      }

      // 检查是否是右括号
      if (!bracket_stack.empty()) {
        std::string expected_right = lt_bracket_pairs.find(text.substr(bracket_stack.top().first, char_len))->second;
        if (current_char == expected_right) {
          // 结束括号段
          int start = bracket_stack.top().first;
          SDL_Color color = bracket_stack.top().second;
          bracket_stack.pop();

          if (start < i) {
            // 添加括号内的内容
            segments.push_back(TextSegmentInfo(start, i, color, false));
          }

          // 添加右括号
          segments.push_back(TextSegmentInfo(i, i + char_len, color, false));
          i += char_len;
          continue;
        }
      }

      i += char_len;
    }

    // 处理剩余的普通文本
    int last_end = 0;
    for (const auto &seg : segments) {
      if (seg.start_byte > last_end) {
        segments.insert(segments.begin(), TextSegmentInfo(last_end, seg.start_byte, text_color, false));
      }
      last_end = seg.end_byte;
    }

    if (last_end < static_cast<int>(text.size())) {
      segments.push_back(TextSegmentInfo(last_end, text.size(), text_color, false));
    }
  } else {
    // 有emoji，合并处理
    int current_pos = 0;

    for (size_t i = 0; i < emoji_positions.size(); i++) {
      int emoji_start = emoji_positions[i].first;
      int emoji_end = emoji_positions[i].second;

      // 添加emoji之前的文本
      if (emoji_start > current_pos) {
        std::string before_text = text.substr(current_pos, emoji_start - current_pos);
        std::vector<TextSegmentInfo> before_segments;
        ParseTextSegments(before_text, {}, {}, text_color, bracket_color, before_segments);

        // 调整位置偏移
        for (auto &seg : before_segments) {
          seg.start_byte += current_pos;
          seg.end_byte += current_pos;
          segments.push_back(seg);
        }
      }

      // 添加emoji
      if (i < emoji_list.size()) {
        segments.push_back(TextSegmentInfo(emoji_start, emoji_end, text_color, true));
      }

      current_pos = emoji_end;
    }

    // 添加最后的文本
    if (current_pos < static_cast<int>(text.size())) {
      std::string remaining_text = text.substr(current_pos);
      std::vector<TextSegmentInfo> remaining_segments;
      ParseTextSegments(remaining_text, {}, {}, text_color, bracket_color, remaining_segments);

      for (auto &seg : remaining_segments) {
        seg.start_byte += current_pos;
        seg.end_byte += current_pos;
        segments.push_back(seg);
      }
    }
  }

  DEBUG_PRINT("Generated %zu text segments", segments.size());
}

// 实现DrawTextWithSegments函数
void ImageLoaderManager::DrawTextWithSegments(SDL_Surface *canvas, const std::string &text, const std::vector<TextSegmentInfo> &segments, TTF_Font *font, int emoji_size, const SDL_Rect &text_rect, AlignMode align_mode, VAlignMode valign_mode,
                                              bool has_shadow, const SDL_Color &shadow_color, int shadow_offset_x, int shadow_offset_y) {
  DEBUG_PRINT("=== DrawTextWithSegments ===");
  DEBUG_PRINT("Text rect: (%d,%d) %dx%d", text_rect.x, text_rect.y, text_rect.w, text_rect.h);

  // 按行组织文本段
  struct LineInfo {
    std::vector<TextSegmentInfo> segments;
    int width;
  };

  std::vector<LineInfo> lines;
  LineInfo current_line;
  int current_width = 0;
  int font_height = TTF_FontHeight(font);

  // 智能换行：根据实际宽度决定换行位置
  for (const auto &seg : segments) {
    if (seg.is_emoji) {
      // Emoji作为一个整体，不能分割
      int seg_width = emoji_size;

      // 检查是否需要换行
      if (current_width + seg_width > text_rect.w && !current_line.segments.empty()) {
        lines.push_back(current_line);
        current_line.segments.clear();
        current_width = 0;
      }

      current_line.segments.push_back(seg);
      current_width += seg_width;
      current_line.width = current_width;
    } else {
      // 普通文本逐字符处理
      int char_pos = seg.start_byte;
      while (char_pos < seg.end_byte) {
        unsigned char c = static_cast<unsigned char>(text[char_pos]);
        int char_len = 1;

        if (c < 0x80)
          char_len = 1;
        else if ((c & 0xE0) == 0xC0)
          char_len = 2;
        else if ((c & 0xF0) == 0xE0)
          char_len = 3;
        else if ((c & 0xF8) == 0xF0)
          char_len = 4;

        std::string single_char = text.substr(char_pos, char_len);
        int char_width;
        TTF_SizeUTF8(font, single_char.c_str(), &char_width, nullptr);

        // 检查是否需要换行
        if (current_width + char_width > text_rect.w && !current_line.segments.empty()) {
          lines.push_back(current_line);
          current_line.segments.clear();
          current_width = 0;
        }

        // 创建单字符片段
        TextSegmentInfo char_seg(char_pos, char_pos + char_len, seg.color, false);

        // 如果当前行为空或最后一个片段不是同一颜色，创建新片段
        if (current_line.segments.empty() || current_line.segments.back().color.r != seg.color.r || current_line.segments.back().color.g != seg.color.g || current_line.segments.back().color.b != seg.color.b ||
            current_line.segments.back().is_emoji != seg.is_emoji) {
          current_line.segments.push_back(char_seg);
        } else {
          // 扩展最后一个片段
          current_line.segments.back().end_byte = char_seg.end_byte;
        }

        current_width += char_width;
        current_line.width = current_width;
        char_pos += char_len;
      }
    }
  }

  // 添加最后一行
  if (!current_line.segments.empty()) {
    lines.push_back(current_line);
  }

  DEBUG_PRINT("Wrapped into %zu lines", lines.size());

  // 计算总高度和垂直起始位置
  int total_height = lines.size() * font_height;
  int current_y = text_rect.y;

  switch (valign_mode) {
  case VAlignMode::MIDDLE:
    current_y += (text_rect.h - total_height) / 2;
    break;
  case VAlignMode::BOTTOM:
    current_y += text_rect.h - total_height;
    break;
  default: // TOP
    break;
  }

  // 绘制每一行
  for (const auto &line : lines) {
    int line_width = line.width;
    int current_x = text_rect.x;

    // 计算水平对齐
    switch (align_mode) {
    case AlignMode::CENTER:
      current_x += (text_rect.w - line_width) / 2;
      break;
    case AlignMode::RIGHT:
      current_x += text_rect.w - line_width;
      break;
    default: // LEFT
      break;
    }

    // 绘制行内的每个片段
    for (const auto &seg : line.segments) {
      if (seg.is_emoji) {
        std::string emoji_text = text.substr(seg.start_byte, seg.end_byte - seg.start_byte);
        SDL_Surface *emoji_surface = LoadEmojiImage(emoji_text, emoji_size);
        if (emoji_surface) {
          // 将emoji垂直居中于文本行
          int emoji_y = current_y + (font_height - emoji_size) / 2;
          SDL_Rect emoji_rect = {current_x, emoji_y, emoji_surface->w, emoji_surface->h};
          SDL_BlitSurface(emoji_surface, nullptr, canvas, &emoji_rect);
          current_x += emoji_surface->w;
          SDL_FreeSurface(emoji_surface);
        } else {
          // emoji图片加载失败，绘制一个灰色方块作为fallback
          DEBUG_PRINT("Failed to load emoji image, drawing fallback square");
          int emoji_y = current_y + (font_height - emoji_size) / 2;
          SDL_Rect fallback_rect = {current_x, emoji_y, emoji_size, emoji_size};
          SDL_FillRect(canvas, &fallback_rect, SDL_MapRGBA(canvas->format, 200, 200, 200, 255));
          current_x += emoji_size;
        }
      } else {
        std::string segment_text = text.substr(seg.start_byte, seg.end_byte - seg.start_byte);

        // 绘制阴影
        if (has_shadow) {
          SDL_Surface *shadow_surface = TTF_RenderUTF8_Blended(font, segment_text.c_str(), shadow_color);
          if (shadow_surface) {
            SDL_Rect shadow_rect = {current_x + shadow_offset_x, current_y + shadow_offset_y, shadow_surface->w, shadow_surface->h};
            SDL_BlitSurface(shadow_surface, nullptr, canvas, &shadow_rect);
            SDL_FreeSurface(shadow_surface);
          }
        }

        // 绘制文本
        SDL_Surface *text_surface = TTF_RenderUTF8_Blended(font, segment_text.c_str(), seg.color);
        if (text_surface) {
          SDL_Rect text_rect = {current_x, current_y, text_surface->w, text_surface->h};
          SDL_BlitSurface(text_surface, nullptr, canvas, &text_rect);
          current_x += text_surface->w;
          SDL_FreeSurface(text_surface);
        }
      }
    }

    current_y += font_height;
  }
}

// 实现EmojiToFileName函数
std::string ImageLoaderManager::EmojiToFileName(const std::string &emoji_text) {
  std::string filename = "emoji_u";

  // 将emoji字符串中的每个码点转换为十六进制
  const char *str = emoji_text.c_str();
  int i = 0;
  while (str[i]) {
    unsigned char c = static_cast<unsigned char>(str[i]);

    // 计算UTF-8字符的码点
    Uint32 codepoint = 0;
    int char_len = 0;

    if (c < 0x80) {
      codepoint = c;
      char_len = 1;
    } else if ((c & 0xE0) == 0xC0) {
      if (str[i + 1]) {
        codepoint = ((c & 0x1F) << 6) | (str[i + 1] & 0x3F);
        char_len = 2;
      }
    } else if ((c & 0xF0) == 0xE0) {
      if (str[i + 1] && str[i + 2]) {
        codepoint = ((c & 0x0F) << 12) | ((str[i + 1] & 0x3F) << 6) | (str[i + 2] & 0x3F);
        char_len = 3;
      }
    } else if ((c & 0xF8) == 0xF0) {
      if (str[i + 1] && str[i + 2] && str[i + 3]) {
        codepoint = ((c & 0x07) << 18) | ((str[i + 1] & 0x3F) << 12) | ((str[i + 2] & 0x3F) << 6) | (str[i + 3] & 0x3F);
        char_len = 4;
      }
    }

    if (codepoint > 0) {
      // 将码点转换为小写十六进制
      char hex[16];
      snprintf(hex, sizeof(hex), "%04x", codepoint);
      if (i > 0)
        filename += "_";
      filename += hex;
    }

    if (char_len > 0) {
      i += char_len;
    } else {
      i++;
    }
  }

  filename += ".png";
  return filename;
}

// 实现LoadEmojiImage函数
SDL_Surface *ImageLoaderManager::LoadEmojiImage(const std::string &emoji_text, int target_size) {
  DEBUG_PRINT("Loading emoji image for: '%s'", emoji_text.c_str());

  std::string filename = EmojiToFileName(emoji_text);
  DEBUG_PRINT("Emoji filename: %s", filename.c_str());

  // 构建完整路径
  char file_path[1024];
  snprintf(file_path, sizeof(file_path), "%s/emoji/%s", assets_path_, filename.c_str());

  DEBUG_PRINT("Emoji file path: %s", file_path);

  // 加载图片
  SDL_Surface *emoji_surface = IMG_Load(file_path);
  if (!emoji_surface) {
    DEBUG_PRINT("Failed to load emoji image: %s", IMG_GetError());

    // 尝试加载不带修饰符的基础版本（如果有修饰符）
    // 例如，emoji_u1f596_1f3fd.png -> emoji_u1f596.png
    size_t last_underscore = filename.rfind('_');
    if (last_underscore != std::string::npos) {
      std::string base_filename = filename.substr(0, last_underscore) + ".png";
      snprintf(file_path, sizeof(file_path), "%s/emoji/%s", assets_path_, base_filename.c_str());
      DEBUG_PRINT("Trying fallback emoji file: %s", file_path);
      emoji_surface = IMG_Load(file_path);
    }

    if (!emoji_surface) {
      DEBUG_PRINT("Fallback emoji image also failed to load");
      return nullptr;
    }
  }

  // 转换为RGBA格式
  SDL_Surface *rgba_surface = SDL_ConvertSurfaceFormat(emoji_surface, SDL_PIXELFORMAT_ABGR8888, 0);
  SDL_FreeSurface(emoji_surface);

  if (!rgba_surface) {
    DEBUG_PRINT("Failed to convert emoji surface to RGBA");
    return nullptr;
  }

  DEBUG_PRINT("Emoji image loaded: %dx%d", rgba_surface->w, rgba_surface->h);

  // 如果需要缩放，调整大小到目标尺寸
  if (target_size > 0 && (rgba_surface->w != target_size || rgba_surface->h != target_size)) {
    SDL_Surface *scaled_surface = SDL_CreateRGBSurfaceWithFormat(0, target_size, target_size, 32, SDL_PIXELFORMAT_ABGR8888);
    if (scaled_surface) {
      // 保持宽高比缩放
      float scale = (static_cast<float>(target_size) / rgba_surface->w < static_cast<float>(target_size) / rgba_surface->h) ? (static_cast<float>(target_size) / rgba_surface->w) : (static_cast<float>(target_size) / rgba_surface->h);
      int new_w = static_cast<int>(rgba_surface->w * scale);
      int new_h = static_cast<int>(rgba_surface->h * scale);
      int offset_x = (target_size - new_w) / 2;
      int offset_y = (target_size - new_h) / 2;

      SDL_Rect dest_rect = {offset_x, offset_y, new_w, new_h};
      SDL_FillRect(scaled_surface, nullptr, SDL_MapRGBA(scaled_surface->format, 0, 0, 0, 0));
      SDL_BlitScaled(rgba_surface, nullptr, scaled_surface, &dest_rect);

      SDL_FreeSurface(rgba_surface);
      rgba_surface = scaled_surface;
      DEBUG_PRINT("Emoji scaled to: %dx%d", rgba_surface->w, rgba_surface->h);
    }
  }

  return rgba_surface;
}

// 修改DrawTextToCanvasWithEmojiAndPositions函数中的字体大小查找部分
void ImageLoaderManager::DrawTextAndEmojiToCanvas(SDL_Surface *canvas, const std::string &text, const std::vector<std::string> &emoji_list, const std::vector<std::pair<int, int>> &emoji_positions, int text_x, int text_y, int text_width, int text_height) {
  DEBUG_PRINT("=== Starting DrawTextAndEmojiToCanvas ===");

  StyleConfig *config = &style_config_;

  // 解析文本段信息（不分割文本）
  std::vector<TextSegmentInfo> segments;
  SDL_Color text_color = {config->text_color[0], config->text_color[1], config->text_color[2], 255};
  SDL_Color bracket_color = {config->bracket_color[0], config->bracket_color[1], config->bracket_color[2], 255};

  ParseTextSegments(text, emoji_list, emoji_positions, text_color, bracket_color, segments);

  DEBUG_PRINT("Text area: %dx%d at (%d,%d)", text_width, text_height, text_x, text_y);

  // 使用二分查找找到合适的字体大小
  int min_font_size = 12;
  int max_font_size = config->font_size;
  int best_font_size = min_font_size;
  TTF_Font *best_font = nullptr;

  DEBUG_PRINT("Starting font size search: min=%d, max=%d", min_font_size, max_font_size);

  // 优化：先尝试最大字号，如果合适就直接使用
  bool font_found = false;

  // 1. 先尝试最大字号
  if (max_font_size >= min_font_size) {
    TTF_Font *max_font = GetFontCached(config->font_family, max_font_size);
    if (max_font) {
      // 测试最大字号是否合适
      int font_height = TTF_FontHeight(max_font);

      // 模拟换行计算
      int current_width = 0;
      int line_count = 1;
      bool fits = true;

      for (const auto &seg : segments) {
        if (seg.is_emoji) {
          // Emoji宽度等于字体高度（近似正方形）
          int seg_width = font_height;

          // 检查是否需要换行
          if (current_width + seg_width > text_width) {
            if (current_width == 0) {
              // Emoji本身宽度就超过文本框
              fits = false;
              break;
            }
            line_count++;
            current_width = seg_width;

            // 检查高度是否超过
            if (line_count * font_height > text_height) {
              fits = false;
              break;
            }
          } else {
            current_width += seg_width;
          }
        } else {
          // 普通文本逐字符处理
          int char_pos = seg.start_byte;
          while (char_pos < seg.end_byte) {
            unsigned char c = static_cast<unsigned char>(text[char_pos]);
            int char_len = 1;

            if (c < 0x80)
              char_len = 1;
            else if ((c & 0xE0) == 0xC0)
              char_len = 2;
            else if ((c & 0xF0) == 0xE0)
              char_len = 3;
            else if ((c & 0xF8) == 0xF0)
              char_len = 4;

            std::string single_char = text.substr(char_pos, char_len);
            int char_width;
            TTF_SizeUTF8(max_font, single_char.c_str(), &char_width, nullptr);

            // 检查是否需要换行
            if (current_width + char_width > text_width) {
              if (current_width == 0) {
                // 单个字符就超过行宽
                fits = false;
                break;
              }
              line_count++;
              current_width = char_width;

              // 检查高度是否超过
              if (line_count * font_height > text_height) {
                fits = false;
                break;
              }
            } else {
              current_width += char_width;
            }

            char_pos += char_len;
          }

          if (!fits)
            break;
        }

        if (!fits)
          break;
      }

      // 最终检查总高度
      if (fits) {
        int total_height = line_count * font_height;
        fits = (total_height <= text_height);
      }

      DEBUG_PRINT("Testing max font size %d: fits=%d, lines=%d, font_height=%d", max_font_size, fits, line_count, font_height);

      if (fits) {
        // 最大字号合适，直接使用
        best_font_size = max_font_size;
        best_font = max_font;
        font_found = true;
        DEBUG_PRINT("Max font size %d fits, using it directly", max_font_size);
      } else {
        // 最大字号不合适，需要尝试更小的
        // 注意：不要关闭字体，字体缓存会管理它
        max_font_size--; // 最大字号不合适，从max-1开始二分查找
      }
    }
  }

  // 2. 如果最大字号不合适，进行二分查找
  if (!font_found) {
    DEBUG_PRINT("Max font size doesn't fit, starting binary search: min=%d, max=%d", min_font_size, max_font_size);

    while (min_font_size <= max_font_size) {
      int current_size = (min_font_size + max_font_size) / 2;
      TTF_Font *test_font = GetFontCached(config->font_family, current_size);

      if (!test_font) {
        DEBUG_PRINT("Failed to get font size %d, trying smaller", current_size);
        max_font_size = current_size - 1;
        continue;
      }

      // 测试当前字体大小是否能适应
      int font_height = TTF_FontHeight(test_font);

      // 模拟换行计算
      int current_width = 0;
      int line_count = 1;
      bool fits = true;

      for (const auto &seg : segments) {
        if (seg.is_emoji) {
          // Emoji宽度等于字体高度（近似正方形）
          int seg_width = font_height;

          // 检查是否需要换行
          if (current_width + seg_width > text_width) {
            if (current_width == 0) {
              // Emoji本身宽度就超过文本框
              fits = false;
              break;
            }
            line_count++;
            current_width = seg_width;

            // 检查高度是否超过
            if (line_count * font_height > text_height) {
              fits = false;
              break;
            }
          } else {
            current_width += seg_width;
          }
        } else {
          // 普通文本逐字符处理
          int char_pos = seg.start_byte;
          while (char_pos < seg.end_byte) {
            unsigned char c = static_cast<unsigned char>(text[char_pos]);
            int char_len = 1;

            if (c < 0x80)
              char_len = 1;
            else if ((c & 0xE0) == 0xC0)
              char_len = 2;
            else if ((c & 0xF0) == 0xE0)
              char_len = 3;
            else if ((c & 0xF8) == 0xF0)
              char_len = 4;

            std::string single_char = text.substr(char_pos, char_len);
            int char_width;
            TTF_SizeUTF8(test_font, single_char.c_str(), &char_width, nullptr);

            // 检查是否需要换行
            if (current_width + char_width > text_width) {
              if (current_width == 0) {
                // 单个字符就超过行宽
                fits = false;
                break;
              }
              line_count++;
              current_width = char_width;

              // 检查高度是否超过
              if (line_count * font_height > text_height) {
                fits = false;
                break;
              }
            } else {
              current_width += char_width;
            }

            char_pos += char_len;
          }

          if (!fits)
            break;
        }

        if (!fits)
          break;
      }

      // 最终检查总高度
      if (fits) {
        int total_height = line_count * font_height;
        fits = (total_height <= text_height);
      }

      DEBUG_PRINT("Testing font size %d: fits=%d, lines=%d, font_height=%d", current_size, fits, line_count, font_height);

      if (fits) {
        // 当前字体大小合适，尝试更大的
        best_font_size = current_size;
        best_font = test_font;
        min_font_size = current_size + 1;
        DEBUG_PRINT("Font size %d fits, trying larger", current_size);
      } else {
        // 当前字体大小不合适，尝试更小的
        max_font_size = current_size - 1;
        DEBUG_PRINT("Font size %d doesn't fit, trying smaller", current_size);
        // 注意：不要关闭字体，字体缓存会管理它
      }
    }
  }

  // 如果没找到合适的字体，使用最小字体
  if (!best_font) {
    best_font_size = 12;
    best_font = GetFontCached(config->font_family, best_font_size);
    if (!best_font) {
      DEBUG_PRINT("ERROR: Failed to get font even at min size");
      return;
    }
    DEBUG_PRINT("No suitable font found, using minimum size %d", best_font_size);
  }

  DEBUG_PRINT("Using font size: %d", best_font_size);

  // 转换对齐模式
  AlignMode align_mode = AlignMode::LEFT;
  if (strcmp(config->text_align, "center") == 0)
    align_mode = AlignMode::CENTER;
  else if (strcmp(config->text_align, "right") == 0)
    align_mode = AlignMode::RIGHT;

  VAlignMode valign_mode = VAlignMode::TOP;
  if (strcmp(config->text_valign, "middle") == 0)
    valign_mode = VAlignMode::MIDDLE;
  else if (strcmp(config->text_valign, "bottom") == 0)
    valign_mode = VAlignMode::BOTTOM;

  // 绘制文本
  SDL_Rect text_rect = {text_x, text_y, text_width, text_height};
  SDL_Color shadow_color = {config->shadow_color[0], config->shadow_color[1], config->shadow_color[2], 255};

  DrawTextWithSegments(canvas, text, segments, best_font, int(TTF_FontHeight(best_font) * 0.9), text_rect, align_mode, valign_mode, config->shadow_offset_x != 0 || config->shadow_offset_y != 0, shadow_color, config->shadow_offset_x,
                       config->shadow_offset_y);

  DEBUG_PRINT("=== Finished DrawTextAndEmojiToCanvas ===");
}

} // namespace image_loader

// C interface export functions
extern "C" {

__declspec(dllexport) void set_global_config(const char *assets_path, float min_image_ratio) { image_loader::ImageLoaderManager::GetInstance().SetGlobalConfig(assets_path, min_image_ratio); }

__declspec(dllexport) void update_gui_settings(const char *settings_json) { image_loader::ImageLoaderManager::GetInstance().UpdateGuiSettings(settings_json); }

__declspec(dllexport) void update_style_config(const char *style_json) { image_loader::ImageLoaderManager::GetInstance().UpdateStyleConfig(style_json); }

__declspec(dllexport) void clear_cache(const char *cache_type) { image_loader::ImageLoaderManager::GetInstance().ClearCache(cache_type); }

__declspec(dllexport) int generate_complete_image(const char *assets_path, int canvas_width, int canvas_height, const char *components_json, const char *character_name, int emotion_index, int background_index, unsigned char **out_data, int *out_width,
                                                  int *out_height) {

  return static_cast<int>(image_loader::ImageLoaderManager::GetInstance().GenerateCompleteImage(assets_path, canvas_width, canvas_height, components_json, character_name, emotion_index, background_index, out_data, out_width, out_height));
}

__declspec(dllexport) int draw_content_simple(const char *text, const char *emoji_json, unsigned char *image_data, int image_width, int image_height, int image_pitch, unsigned char **out_data, int *out_width, int *out_height) {
  return static_cast<int>(image_loader::ImageLoaderManager::GetInstance().DrawContentWithTextAndImage(text, emoji_json, image_data, image_width, image_height, image_pitch, out_data, out_width, out_height));
}

__declspec(dllexport) void free_image_data(unsigned char *data) {
  if (data) {
    free(data);
  }
}

__declspec(dllexport) void cleanup_all() { image_loader::ImageLoaderManager::GetInstance().Cleanup(); }

__declspec(dllexport) void cleanup_renderer() { image_loader::ImageLoaderManager::GetInstance().CleanupRenderer(); }

} // extern "C"