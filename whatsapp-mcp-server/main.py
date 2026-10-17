from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from whatsapp import (
    search_contacts as whatsapp_search_contacts,
    list_messages as whatsapp_list_messages,
    list_chats as whatsapp_list_chats,
    get_chat as whatsapp_get_chat,
    get_direct_chat_by_contact as whatsapp_get_direct_chat_by_contact,
    get_contact_chats as whatsapp_get_contact_chats,
    get_last_interaction as whatsapp_get_last_interaction,
    get_message_context as whatsapp_get_message_context,
    send_message as whatsapp_send_message,
    send_file as whatsapp_send_file,
    send_audio_message as whatsapp_audio_voice_message,
    download_media as whatsapp_download_media
)

from whatsapp import delete_whatsapp_message, bridge_action

# Initialize FastMCP server
mcp = FastMCP("whatsapp")

# Media viewing and older-history tools
import media_tools
media_tools.register(mcp)

@mcp.tool()
def search_contacts(query: str) -> Any:
    """Search WhatsApp contacts by name or phone number.
    
    Args:
        query: Search term to match against contact names or phone numbers
    """
    contacts = whatsapp_search_contacts(query)
    return contacts

@mcp.tool()
def list_messages(
    after: Optional[str] = None,
    before: Optional[str] = None,
    sender_phone_number: Optional[str] = None,
    chat_jid: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    page: int = 0,
    include_context: bool = True,
    context_before: int = 1,
    context_after: int = 1
) -> Any:
    """Get WhatsApp messages matching specified criteria with optional context.
    
    Args:
        after: Optional ISO-8601 formatted string to only return messages after this date
        before: Optional ISO-8601 formatted string to only return messages before this date
        sender_phone_number: Optional phone number to filter messages by sender
        chat_jid: Optional chat JID to filter messages by chat
        query: Optional search term to filter messages by content
        limit: Maximum number of messages to return (default 20)
        page: Page number for pagination (default 0)
        include_context: Whether to include messages before and after matches (default True)
        context_before: Number of messages to include before each match (default 1)
        context_after: Number of messages to include after each match (default 1)
    """
    messages = whatsapp_list_messages(
        after=after,
        before=before,
        sender_phone_number=sender_phone_number,
        chat_jid=chat_jid,
        query=query,
        limit=limit,
        page=page,
        include_context=include_context,
        context_before=context_before,
        context_after=context_after
    )
    return messages

@mcp.tool()
def list_chats(
    query: Optional[str] = None,
    limit: int = 20,
    page: int = 0,
    include_last_message: bool = True,
    sort_by: str = "last_active"
) -> Any:
    """Get WhatsApp chats matching specified criteria.
    
    Args:
        query: Optional search term to filter chats by name or JID
        limit: Maximum number of chats to return (default 20)
        page: Page number for pagination (default 0)
        include_last_message: Whether to include the last message in each chat (default True)
        sort_by: Field to sort results by, either "last_active" or "name" (default "last_active")
    """
    chats = whatsapp_list_chats(
        query=query,
        limit=limit,
        page=page,
        include_last_message=include_last_message,
        sort_by=sort_by
    )
    return chats

@mcp.tool()
def get_chat(chat_jid: str, include_last_message: bool = True) -> Any:
    """Get WhatsApp chat metadata by JID.
    
    Args:
        chat_jid: The JID of the chat to retrieve
        include_last_message: Whether to include the last message (default True)
    """
    chat = whatsapp_get_chat(chat_jid, include_last_message)
    return chat

@mcp.tool()
def get_direct_chat_by_contact(sender_phone_number: str) -> Any:
    """Get WhatsApp chat metadata by sender phone number.
    
    Args:
        sender_phone_number: The phone number to search for
    """
    chat = whatsapp_get_direct_chat_by_contact(sender_phone_number)
    return chat

@mcp.tool()
def get_contact_chats(jid: str, limit: int = 20, page: int = 0) -> Any:
    """Get all WhatsApp chats involving the contact.
    
    Args:
        jid: The contact's JID to search for
        limit: Maximum number of chats to return (default 20)
        page: Page number for pagination (default 0)
    """
    chats = whatsapp_get_contact_chats(jid, limit, page)
    return chats

@mcp.tool()
def get_last_interaction(jid: str) -> str:
    """Get most recent WhatsApp message involving the contact.
    
    Args:
        jid: The JID of the contact to search for
    """
    message = whatsapp_get_last_interaction(jid)
    return message

@mcp.tool()
def get_message_context(
    message_id: str,
    before: int = 5,
    after: int = 5
) -> Dict[str, Any]:
    """Get context around a specific WhatsApp message.
    
    Args:
        message_id: The ID of the message to get context for
        before: Number of messages to include before the target message (default 5)
        after: Number of messages to include after the target message (default 5)
    """
    context = whatsapp_get_message_context(message_id, before, after)
    return context

@mcp.tool()
def send_message(
    recipient: str,
    message: str
) -> Dict[str, Any]:
    """Send a WhatsApp message to a person or group. For group chats use the JID.

    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        message: The message text to send
    
    Returns:
        A dictionary containing success status and a status message
    """
    # Validate input
    if not recipient:
        return {
            "success": False,
            "message": "Recipient must be provided"
        }
    
    # Call the whatsapp_send_message function with the unified recipient parameter
    success, status_message = whatsapp_send_message(recipient, message)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
def send_file(recipient: str, media_path: str) -> Dict[str, Any]:
    """Send a file such as a picture, raw audio, video or document via WhatsApp to the specified recipient. For group messages use the JID.
    
    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        media_path: The absolute path to the media file to send (image, video, document)
    
    Returns:
        A dictionary containing success status and a status message
    """
    
    # Call the whatsapp_send_file function
    success, status_message = whatsapp_send_file(recipient, media_path)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
def send_audio_message(recipient: str, media_path: str) -> Dict[str, Any]:
    """Send any audio file as a WhatsApp audio message to the specified recipient. For group messages use the JID. If it errors due to ffmpeg not being installed, use send_file instead.
    
    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        media_path: The absolute path to the audio file to send (will be converted to Opus .ogg if it's not a .ogg file)
    
    Returns:
        A dictionary containing success status and a status message
    """
    success, status_message = whatsapp_audio_voice_message(recipient, media_path)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
def download_media(message_id: str, chat_jid: str) -> Dict[str, Any]:
    """Download media from a WhatsApp message and get the local file path.
    
    Args:
        message_id: The ID of the message containing the media
        chat_jid: The JID of the chat containing the message
    
    Returns:
        A dictionary containing success status, a status message, and the file path if successful
    """
    file_path = whatsapp_download_media(message_id, chat_jid)
    
    if file_path:
        return {
            "success": True,
            "message": "Media downloaded successfully",
            "file_path": file_path
        }
    else:
        return {
            "success": False,
            "message": "Failed to download media"
        }

@mcp.tool()
def delete_message(
    chat_jid: str,
    message_id: str
) -> Dict[str, Any]:
    """Delete a message you sent, for everyone in the chat.

    Only works for messages sent through this server after it was updated to record sent messages.
    Use the chat JID and message ID from list_messages or from the send_message result.

    Args:
        chat_jid: The chat the message is in, e.g. "15551234567@s.whatsapp.net"
        message_id: The ID of the message to delete
    """
    success, message = delete_whatsapp_message(chat_jid, message_id)
    return {"success": success, "message": message}


@mcp.tool()
def list_groups() -> Dict[str, Any]:
    """List the group chats you are a member of, with their JIDs and names."""
    success, message, data = bridge_action("group/joined", {})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def get_group_info(group_jid: str) -> Dict[str, Any]:
    """Get a group's name, description, settings and participants (with admin flags).

    Also reports is_community (a Community parent group) and parent_community (set for a Community's
    announcement group). Name, lock and only-admins-send changes are rejected for those.

    Args:
        group_jid: The group JID, e.g. "123456789012345678@g.us"
    """
    success, message, data = bridge_action("group/info", {"group_jid": group_jid})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def check_on_whatsapp(phone_numbers: List[str]) -> Dict[str, Any]:
    """Check which phone numbers have a WhatsApp account, and get their JIDs.

    Args:
        phone_numbers: Phone numbers with country code, no +
    """
    success, message, data = bridge_action("check_whatsapp", {"phones": phone_numbers})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def get_user_info(jids: List[str]) -> Dict[str, Any]:
    """Get the status text and profile picture ID for WhatsApp users.

    Args:
        jids: Phone numbers with country code, no +, or full JIDs
    """
    success, message, data = bridge_action("user_info", {"jids": jids})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def edit_message(chat_jid: str, message_id: str, new_text: str) -> Dict[str, Any]:
    """Edit a message you sent, within WhatsApp's edit time limit.

    Args:
        chat_jid: The chat the message is in, e.g. "15551234567@s.whatsapp.net"
        message_id: The ID of the message to edit
        new_text: The replacement text
    """
    success, message, data = bridge_action("edit", {"chat_jid": chat_jid, "message_id": message_id, "text": new_text})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def react_to_message(chat_jid: str, message_id: str, emoji: str, sender_jid: str = "") -> Dict[str, Any]:
    """React to a message with an emoji. Use an empty emoji to remove your reaction.

    Args:
        chat_jid: The chat the message is in
        message_id: The ID of the message to react to
        emoji: A single emoji such as "👍", or "" to remove the reaction
        sender_jid: Sender of the message when reacting to someone else's message in a group; leave empty for your own messages
    """
    success, message, data = bridge_action(
        "react",
        {"chat_jid": chat_jid, "message_id": message_id, "emoji": emoji, "sender_jid": sender_jid},
    )
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def mark_as_read(chat_jid: str, message_ids: List[str], sender_jid: str = "") -> Dict[str, Any]:
    """Send read receipts for messages in a chat.

    Args:
        chat_jid: The chat the messages are in
        message_ids: IDs of the messages to mark as read
        sender_jid: Sender of the messages in a group chat; leave empty for direct chats
    """
    success, message, data = bridge_action(
        "mark_read",
        {"chat_jid": chat_jid, "message_ids": message_ids, "sender_jid": sender_jid},
    )
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def create_group(name: str, participants: List[str]) -> Dict[str, Any]:
    """Create a new WhatsApp group. You become its admin.

    Args:
        name: Group name (WhatsApp limits it to 25 characters)
        participants: Phone numbers with country code, no +, e.g. ["15551234567"]
    """
    success, message, data = bridge_action("group/create", {"name": name, "participants": participants})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def update_group_participants(group_jid: str, action: str, participants: List[str]) -> Dict[str, Any]:
    """Add, remove, promote or demote members of a group. You need admin rights.

    Args:
        group_jid: The group JID
        action: One of "add", "remove", "promote", "demote"
        participants: Phone numbers with country code, no +, or full JIDs
    """
    success, message, data = bridge_action(
        "group/participants",
        {"group_jid": group_jid, "action": action, "participants": participants},
    )
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_group_name(group_jid: str, name: str) -> Dict[str, Any]:
    """Rename a group. You need admin rights if the group restricts info edits.

    Args:
        group_jid: The group JID
        name: The new group name
    """
    success, message, data = bridge_action("group/name", {"group_jid": group_jid, "name": name})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_group_description(group_jid: str, description: str) -> Dict[str, Any]:
    """Set a group's description (topic). Use an empty string to clear it.

    Args:
        group_jid: The group JID
        description: The new description
    """
    success, message, data = bridge_action("group/topic", {"group_jid": group_jid, "topic": description})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_group_only_admins_send(group_jid: str, enabled: bool) -> Dict[str, Any]:
    """Turn on or off the setting that only admins can send messages in a group.

    Args:
        group_jid: The group JID
        enabled: True to restrict sending to admins, False to let everyone send
    """
    success, message, data = bridge_action("group/announce", {"group_jid": group_jid, "enabled": enabled})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_group_only_admins_edit(group_jid: str, enabled: bool) -> Dict[str, Any]:
    """Turn on or off the setting that only admins can edit group info (name, description, photo).

    Args:
        group_jid: The group JID
        enabled: True to restrict edits to admins, False to let everyone edit
    """
    success, message, data = bridge_action("group/locked", {"group_jid": group_jid, "enabled": enabled})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def leave_group(group_jid: str) -> Dict[str, Any]:
    """Leave a group chat. Other members see that you left.

    A group's owner, and Communities with their announcement groups, cannot be left this way: WhatsApp ignores
    the request. Deactivate a Community in the WhatsApp app instead (get_group_info shows is_community).

    Args:
        group_jid: The group JID
    """
    success, message, data = bridge_action("leave", {"group_jid": group_jid})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_typing(chat_jid: str, typing: bool) -> Dict[str, Any]:
    """Show or hide the 'typing...' indicator in a chat.

    Args:
        chat_jid: The chat to show the indicator in
        typing: True to show 'typing...', False to stop it
    """
    success, message, data = bridge_action("presence", {"chat_jid": chat_jid, "typing": typing})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def block_contact(jid: str, block: bool) -> Dict[str, Any]:
    """Block or unblock a WhatsApp contact.

    Args:
        jid: Phone number with country code, no +, or a full JID
        block: True to block, False to unblock
    """
    success, message, data = bridge_action("block", {"jid": jid, "block": block})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def reply_to_message(
    chat_jid: str,
    message_id: str,
    text: str,
    sender_jid: str = "",
    quoted_text: str = ""
) -> Dict[str, Any]:
    """Reply to a specific message, shown as a quoted reply.

    Args:
        chat_jid: The chat the message is in
        message_id: The ID of the message to reply to
        text: The reply text
        sender_jid: Who sent the quoted message. Required in groups and when quoting your own message; leave empty to quote the other person in a direct chat
        quoted_text: Optional text of the quoted message, so the quote shows its content
    """
    success, message, data = bridge_action(
        "reply",
        {"chat_jid": chat_jid, "message_id": message_id, "text": text, "sender_jid": sender_jid, "quoted_text": quoted_text},
    )
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def send_location(
    chat_jid: str,
    latitude: float,
    longitude: float,
    name: str = "",
    address: str = ""
) -> Dict[str, Any]:
    """Send a map location.

    Args:
        chat_jid: The chat to send to
        latitude: Latitude in degrees (-90 to 90)
        longitude: Longitude in degrees (-180 to 180)
        name: Optional place name
        address: Optional address line
    """
    success, message, data = bridge_action(
        "send_location",
        {"chat_jid": chat_jid, "latitude": latitude, "longitude": longitude, "name": name, "address": address},
    )
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def send_contact(chat_jid: str, contact_name: str, contact_phone: str) -> Dict[str, Any]:
    """Send a contact card.

    Args:
        chat_jid: The chat to send to
        contact_name: Display name on the card
        contact_phone: Phone number with country code, e.g. "15551234567"
    """
    success, message, data = bridge_action(
        "send_contact",
        {"chat_jid": chat_jid, "contact_name": contact_name, "contact_phone": contact_phone},
    )
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def send_poll(
    chat_jid: str,
    question: str,
    options: List[str],
    selectable_count: int = 1
) -> Dict[str, Any]:
    """Send a poll.

    Args:
        chat_jid: The chat to send to
        question: The poll question
        options: Between 2 and 12 answer options
        selectable_count: How many options a person may pick (default 1)
    """
    success, message, data = bridge_action(
        "send_poll",
        {"chat_jid": chat_jid, "question": question, "options": options, "selectable_count": selectable_count},
    )
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_disappearing_messages(chat_jid: str, seconds: int) -> Dict[str, Any]:
    """Set the disappearing-messages timer for a chat.

    Args:
        chat_jid: The chat to change
        seconds: 0 to turn off, otherwise 86400 (24 hours), 604800 (7 days) or 7776000 (90 days)
    """
    success, message, data = bridge_action("disappearing", {"chat_jid": chat_jid, "seconds": seconds})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def get_group_invite_link(group_jid: str, reset: bool = False) -> Dict[str, Any]:
    """Get a group's invite link. You need admin rights.

    Args:
        group_jid: The group JID
        reset: True to revoke the old link and create a new one (the old link stops working)
    """
    success, message, data = bridge_action("group/invite", {"group_jid": group_jid, "reset": reset})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def preview_group_invite(invite_link: str) -> Dict[str, Any]:
    """Look up a group from an invite link without joining it.

    Args:
        invite_link: A chat.whatsapp.com link or just its code
    """
    success, message, data = bridge_action("group/link_info", {"link": invite_link})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def join_group_with_link(invite_link: str) -> Dict[str, Any]:
    """Join a group using an invite link. Other members see that you joined.

    Args:
        invite_link: A chat.whatsapp.com link or just its code
    """
    success, message, data = bridge_action("group/join", {"link": invite_link})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_about_text(text: str) -> Dict[str, Any]:
    """Set your WhatsApp 'About' text.

    Args:
        text: The new About text
    """
    if not text.strip():
        return {
            "success": False,
            "message": "About text is blank. WhatsApp returned an error for a blank About, so give it real text.",
            "data": None,
        }
    success, message, data = bridge_action("status", {"text": text})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def get_profile_picture(jid: str) -> Dict[str, Any]:
    """Get the download URL of a user's or group's profile picture.

    Args:
        jid: Phone number with country code, no +, or a full JID
    """
    success, message, data = bridge_action("profile_picture", {"jid": jid})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def set_presence(available: bool) -> Dict[str, Any]:
    """Appear online or offline.

    Args:
        available: True to appear online, False to appear offline
    """
    success, message, data = bridge_action("set_presence", {"available": available})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def get_privacy_settings() -> Dict[str, Any]:
    """Read your WhatsApp privacy settings (last seen, profile photo, read receipts, who can add you to groups...)."""
    success, message, data = bridge_action("privacy", {})
    return {"success": success, "message": message, "data": data}


@mcp.tool()
def get_blocklist() -> Dict[str, Any]:
    """List the contacts you have blocked."""
    success, message, data = bridge_action("blocklist", {})
    return {"success": success, "message": message, "data": data}


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')