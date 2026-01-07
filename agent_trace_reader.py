from langchain.tools import tool
from pathlib import Path
import json
from smartagent.workspace import resolve_workspace_path

@tool(parse_docstring=True)
def agent_trace_processor(virtual_json_path: str, output_virtual_path: str = None) -> dict:
    """
    [CRITICAL TOOL] Process 'Agent Trace' JSON files and SAVE the result.
    
    This tool reads a raw trace file, extracts key information (Goal, Facts, Analysis),
    and saves the structured summary to a new JSON file.
    
    Args:
        virtual_json_path: Input path to the raw trace JSON (e.g., `/workspace/test.json`).
        output_virtual_path: (Optional) Output path to save the processed result 
                             (e.g., `/workspace/summary.json`). 
                             If not provided, it defaults to `processed_trace.json` in the same dir.
    
    Returns:
        dict: The extracted data and the status of the file save operation.
    """
    
    # --- 1. 读取与路径解析 (Reading Logic) ---
    try:
        input_path = resolve_workspace_path(virtual_json_path)
    except Exception as e:
        return {"status": "error", "error": f"Input path resolution failed: {str(e)}"}

    if not input_path.exists():
        return {"status": "error", "error": f"File not found: {virtual_json_path}"}

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "error", "error": f"Error reading JSON: {str(e)}"}

    # --- 2. 数据兼容处理 (Fix for 'list' object error) ---
    # 场景 A: {"fullContent": [...]}
    if isinstance(data, dict):
        full_content = data.get("fullContent", [])
    # 场景 B: [{}, {}, ...]
    elif isinstance(data, list):
        full_content = data
    else:
        return {"status": "error", "error": "JSON root is neither a list nor a dict."}
    
    if not isinstance(full_content, list):
        return {"status": "error", "error": "'fullContent' is not a list."}

    # --- 3. 信息提取 (Extraction Logic) ---
    user_goal = ""
    gathered_facts = []
    previous_analyses = []
    links_to_text = []

    for msg in full_content:
        if not isinstance(msg, dict): continue

        role = msg.get("role")
        task_type = msg.get("taskType")
        content = msg.get("content")
        msg_id = msg.get("id")

        # Extract User Goal
        if msg_id == 1 and role == "client":
            user_goal = str(content)

        # Extract Search Results
        if task_type == "search" and isinstance(content, dict):
            sub_task = content.get("subTask", "Unknown")
            answer = content.get("answer", "")
            citations = content.get("citation", [])
            
            # Link mapping
            for citation in citations:
                if isinstance(citation, dict):
                    link = citation.get("url", "#")
                    links_to_text.append(f"Sub-task: {sub_task}, Answer: {answer[:50]}..., Link: {link}")

            # Fact block
            source_lines = [f"[{c.get('index', '?')}] {c.get('title', 'Source')}" for c in citations if isinstance(c, dict)]
            fact_block = {
                "topic": sub_task,
                "findings": answer,
                "sources": source_lines
            }
            gathered_facts.append(fact_block)

        # Extract Analysis
        if task_type == "analyze" and role == "server":
            analysis_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            previous_analyses.append({"step_id": msg_id, "analysis": analysis_text})

    # --- 4. 构造结果对象 (Result Construction) ---
    processed_result = {
        "source_file": virtual_json_path,
        "user_goal": user_goal,
        "gathered_facts": gathered_facts,
        "previous_analyses": previous_analyses,
        "links_to_text": links_to_text
    }

    # --- 5. 保存结果文件 (Saving Logic) ---
    try:
        # 如果没有提供输出路径，默认生成一个名字
        if not output_virtual_path:
            input_filename = input_path.stem # e.g., 'test' from 'test.json'
            output_virtual_path = f"/workspace/{input_filename}_processed.json"

        save_path = resolve_workspace_path(output_virtual_path)
        
        # 确保父目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(processed_result, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        return {
            "status": "partial_success", 
            "extracted_data": processed_result,
            "save_error": f"Failed to save file: {str(e)}"
        }

    return {
        "status": "success",
        "message": f"Successfully processed and saved to {output_virtual_path}",
        "saved_path": output_virtual_path,
        "data_preview": {
            "goal": user_goal,
            "facts_count": len(gathered_facts)
        }
    }
