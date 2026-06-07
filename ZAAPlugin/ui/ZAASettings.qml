import QtQuick 6.0
import QtQuick.Controls 6.0
import QtQuick.Layouts 6.0

import UM 1.6 as UM
import Cura 1.7 as Cura

UM.Dialog
{
    id: zaaDialog
    title: "Z Anti-Aliasing Settings"

    minimumWidth: screenScaleFactor * 400
    minimumHeight: (screenScaleFactor * contents.childrenRect.height) + (2 * UM.Theme.getSize("default_margin").height) + UM.Theme.getSize("button").height
    width: minimumWidth
    height: minimumHeight

    backgroundColor: UM.Theme.getColor("main_background")

    property var preferences: UM.Preferences

    ColumnLayout
    {
        id: contents
        width: zaaDialog.width - 2 * UM.Theme.getSize("default_margin").width
        spacing: UM.Theme.getSize("default_margin").height

        UM.CheckBox
        {
            id: enabledCheckbox
            text: "Enable Z Anti-Aliasing"
            checked: preferences.getValue("zaa/enabled")
        }

        // Parameters section
        UM.Label
        {
            text: "Parameters"
            font.bold: true
        }

        GridLayout
        {
            columns: 2
            rowSpacing: UM.Theme.getSize("default_lining").height
            columnSpacing: UM.Theme.getSize("default_margin").width
            Layout.fillWidth: true
            enabled: enabledCheckbox.checked

            UM.Label
            {
                text: "Resolution (mm):"
            }
            Cura.TextField
            {
                id: resolutionField
                Layout.preferredWidth: 100
                text: preferences.getValue("zaa/resolution")
                validator: RegularExpressionValidator { regularExpression: /[0-9]*(\.[0-9]+)?/ }
            }
        }

        // Target Regions section
        UM.Label
        {
            text: "Target Regions"
            font.bold: true
        }

        ColumnLayout
        {
            spacing: UM.Theme.getSize("default_lining").height
            enabled: enabledCheckbox.checked

            UM.CheckBox
            {
                id: topSurfaceCheck
                text: "TOP-SURFACE-SKIN (recommended)"
                checked: true
                Component.onCompleted: checked = preferences.getValue("zaa/target_types").indexOf("TOP-SURFACE-SKIN") >= 0
            }
            UM.CheckBox
            {
                id: skinCheck
                text: "SKIN"
                checked: false
                Component.onCompleted:
                {
                    var types = preferences.getValue("zaa/target_types")
                    checked = types.indexOf(",SKIN") >= 0 || types === "SKIN" || types.indexOf("SKIN,") === 0
                }
            }
            UM.CheckBox
            {
                id: wallOuterCheck
                text: "WALL-OUTER"
                checked: false
                Component.onCompleted: checked = preferences.getValue("zaa/target_types").indexOf("WALL-OUTER") >= 0
            }
        }

        UM.CheckBox
        {
            id: collisionCheckbox
            text: "Enable collision detection"
            checked: preferences.getValue("zaa/enable_collision")
            enabled: enabledCheckbox.checked
        }
    }

    rightButtons:
    [
        Cura.SecondaryButton
        {
            text: "Cancel"
            onClicked: zaaDialog.reject()
        },
        Cura.PrimaryButton
        {
            text: "OK"
            onClicked: zaaDialog.accept()
        }
    ]

    onAccepted:
    {
        preferences.setValue("zaa/enabled", enabledCheckbox.checked)
        preferences.setValue("zaa/resolution", parseFloat(resolutionField.text) || 0.5)
        preferences.setValue("zaa/enable_collision", collisionCheckbox.checked)

        var types = []
        if (topSurfaceCheck.checked) types.push("TOP-SURFACE-SKIN")
        if (skinCheck.checked) types.push("SKIN")
        if (wallOuterCheck.checked) types.push("WALL-OUTER")
        preferences.setValue("zaa/target_types", types.join(","))
    }
}
