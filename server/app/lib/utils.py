
def add_message(messages: list, message: str):
    if not message:
        return messages
    
    if not messages or len(messages) == 0:
        messages.append(message)
        return messages
    
    last_message = messages[-1]
    
    if message["role"] == last_message["role"]:
        last_message["content"] += f" {message['content']}"
    else:
        messages.append(message)
