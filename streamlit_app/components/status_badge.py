import streamlit as st

def status_badge(status: str) -> None:
    """
    显示状态徽章
    
    参数:
    status: 状态文本
    """
    status = status.lower()
    
    if status == "pending":
        st.markdown(
            f"""<span style="background-color: #FFA500; color: white; padding: 3px 8px; 
            border-radius: 4px; font-size: 0.8em; font-weight: bold;">等待中</span>""",
            unsafe_allow_html=True
        )
    elif status == "processing":
        st.markdown(
            f"""<span style="background-color: #1E90FF; color: white; padding: 3px 8px; 
            border-radius: 4px; font-size: 0.8em; font-weight: bold;">处理中</span>""",
            unsafe_allow_html=True
        )
    elif status == "completed":
        st.markdown(
            f"""<span style="background-color: #2E8B57; color: white; padding: 3px 8px; 
            border-radius: 4px; font-size: 0.8em; font-weight: bold;">已完成</span>""",
            unsafe_allow_html=True
        )
    elif status == "completed_with_errors":
        st.markdown(
            f"""<span style="background-color: #DAA520; color: white; padding: 3px 8px; 
            border-radius: 4px; font-size: 0.8em; font-weight: bold;">完成(含错误)</span>""",
            unsafe_allow_html=True
        )
    elif status == "failed":
        st.markdown(
            f"""<span style="background-color: #DC143C; color: white; padding: 3px 8px; 
            border-radius: 4px; font-size: 0.8em; font-weight: bold;">失败</span>""",
            unsafe_allow_html=True
        )
    elif status == "canceled":
        st.markdown(
            f"""<span style="background-color: #808080; color: white; padding: 3px 8px; 
            border-radius: 4px; font-size: 0.8em; font-weight: bold;">已取消</span>""",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""<span style="background-color: #555555; color: white; padding: 3px 8px; 
            border-radius: 4px; font-size: 0.8em; font-weight: bold;">{status}</span>""",
            unsafe_allow_html=True
        )

def inline_status_badge(status: str) -> str:
    """
    返回表示状态徽章的HTML代码，用于表格中显示
    
    参数:
    status: 状态文本
    
    返回:
    HTML代码
    """
    status = status.lower()
    
    if status == "pending":
        return f"""<span style="background-color: #FFA500; color: white; padding: 2px 6px; 
                border-radius: 3px; font-size: 0.8em; font-weight: bold;">等待中</span>"""
    elif status == "processing":
        return f"""<span style="background-color: #1E90FF; color: white; padding: 2px 6px; 
                border-radius: 3px; font-size: 0.8em; font-weight: bold;">处理中</span>"""
    elif status == "completed":
        return f"""<span style="background-color: #2E8B57; color: white; padding: 2px 6px; 
                border-radius: 3px; font-size: 0.8em; font-weight: bold;">已完成</span>"""
    elif status == "completed_with_errors":
        return f"""<span style="background-color: #DAA520; color: white; padding: 2px 6px; 
                border-radius: 3px; font-size: 0.8em; font-weight: bold;">完成(含错误)</span>"""
    elif status == "failed":
        return f"""<span style="background-color: #DC143C; color: white; padding: 2px 6px; 
                border-radius: 3px; font-size: 0.8em; font-weight: bold;">失败</span>"""
    elif status == "canceled":
        return f"""<span style="background-color: #808080; color: white; padding: 2px 6px; 
                border-radius: 3px; font-size: 0.8em; font-weight: bold;">已取消</span>"""
    else:
        return f"""<span style="background-color: #555555; color: white; padding: 2px 6px; 
                border-radius: 3px; font-size: 0.8em; font-weight: bold;">{status}</span>""" 