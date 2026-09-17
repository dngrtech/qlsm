Steam Workshop ID Detection & Preview
Summary

Add support for detecting Steam Workshop item IDs directly within the config editor.

When a user highlights a sequence of 8–11 numerical characters, the editor will treat the selection as a potential Steam Workshop item ID and provide a quick preview of the associated Workshop item.

Motivation

Config files may contain Steam Workshop IDs, but currently users have to manually copy the number, open a browser, construct the Workshop URL, and look up the item themselves.

This feature would make those IDs more useful and discoverable directly from within the config editor.

Proposed Behavior

When the user highlights an 8–11 digit number:

Detect the highlighted value as a potential Steam Workshop ID.

Construct the corresponding Workshop URL:

https://steamcommunity.com/sharedfiles/filedetails/?id=<WORKSHOP_ID>


Retrieve the publicly available Workshop page.

Parse relevant metadata from the page.

Display the information in a popup within the editor.

Example

If the user highlights:

123456789


The editor would construct:

https://steamcommunity.com/sharedfiles/filedetails/?id=123456789


The resulting popup could display:

┌─────────────────────────────────────┐
│ Example Workshop Item               │
│                                     │
│ [ Workshop Thumbnail ]              │
│                                     │
│ Description of the Workshop item... │
│                                     │
│        Open in Steam →              │
└─────────────────────────────────────┘

Metadata

The initial implementation could retrieve the following information:

Title

Description

Thumbnail / Workshop image

Workshop URL

The Workshop title appears to be contained within:

<div class="workshopItemTitle">
    ...
</div>


Additional selectors could be identified for the description and image URL.

UX Considerations

Only trigger detection when the user has an active text selection.

The selection must contain only numerical characters.

The selected value must be between 8 and 11 digits.

Invalid or nonexistent Workshop IDs should fail gracefully.

Network requests should be asynchronous and should not block the config editor.

Display a loading state while Workshop information is being retrieved.

The popup should be easily dismissed.

Provide an Open in Steam action to access the complete Workshop page.

Technical Considerations
Workshop ID Detection

A simple validation rule could be used:

^\d{8,11}$


This ensures that only selections containing 8–11 digits are considered.

URL Construction
https://steamcommunity.com/sharedfiles/filedetails/?id=<WORKSHOP_ID>


Where <WORKSHOP_ID> is the selected numeric value.

HTML Parsing

The implementation could parse the publicly accessible Workshop page to extract the required metadata.

For example:

<div class="workshopItemTitle">
    Workshop Item Title
</div>


The implementation should account for the possibility that Steam's HTML structure may change over time.

Acceptance Criteria

 Selecting an 8–11 digit number triggers Workshop ID detection.

 Selections containing non-numeric characters are ignored.

 Numbers outside the 8–11 digit range are ignored.

 The correct Steam Workshop URL is generated.

 The Workshop title is displayed in the preview.

 The Workshop description is displayed when available.

 The Workshop thumbnail is displayed when available.

 Invalid or nonexistent Workshop IDs are handled gracefully.

 The user can open the Workshop item in Steam.

 Workshop lookups do not block normal config editing.

Future Enhancements

Potential follow-up improvements could include:

Automatic detection of Workshop IDs without requiring text selection.

Caching Workshop metadata to avoid repeated requests.

Displaying the Workshop author.

Displaying Workshop tags/categories.

Displaying additional Workshop metadata.

Adding a keyboard shortcut to open the Workshop preview.

Allowing detected Workshop IDs to be clicked directly within the editor.

Alternatives Considered

An alternative would be to provide a context-menu action such as "Open as Steam Workshop Item".

However, automatically recognizing a selected 8–11 digit value would provide a more seamless workflow while still requiring an explicit user selection before performing a lookup.

Testing Plan

The following cases should be tested:

Input	Expected Result
12345678	Detect as Workshop ID
123456789	Detect as Workshop ID
12345678901	Detect as Workshop ID
1234567	Ignore
123456789012	Ignore
12345abc	Ignore
12345678abc	Ignore
Nonexistent Workshop ID	Show graceful error/empty state
Valid Workshop ID	Display Workshop metadata
Notes

This proposal is intended as an initial implementation. The exact HTML selectors and parsing strategy may need to be adjusted based on Steam's current Workshop page structure and any restrictions around retrieving/parsing the page.
