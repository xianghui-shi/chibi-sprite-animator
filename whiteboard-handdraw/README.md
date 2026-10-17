# whiteboard-handdraw（白板手绘分支）

口播/SRT 字幕 → 一笔笔画出场景的手绘白板视频。用法见上级 `SKILL.md` 的「分支 W」。

来源与署名：渲染引擎（`stream_render.py`、`render_stream_whiteboard.py`、`parse_srt.py`、`merge_scenes.py`、`prepare_env.py`、`assets/preview.html`）改编自 geeklee/srt-whiteboard-animation（MIT，见 `UPSTREAM-LICENSE`）。
本仓库的改动：新增 `transcribe_srt.py`（音频转字幕）、`make_annotation.py`（逐句区域标注）、`demo_scene.py`（代码画线稿示例）；`render_annotation_preview.py` 增加跨平台字体回退；`assets/drawing-hand.png` 去掉了原笔杆上的文字。
