---
title: Conservation International
summary:
    - Jeremy Prior
    - Ketan Bamniya
date:
some_url:
copyright:
contact:
license: This program is free software; you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation; either version 3 of the License, or (at your option) any later version.
---

# Step4: Select outputs and processing options

1. **Step 4:** `Step 4` guides the user to select the outputs to be saved into the file system for report generation. By clicking on the `Step 4` option, the user will navigate to the section dedicated to producing outputs. Here, the user finds a list of available outputs, each representing data that can be included in the report.

    When the user selects an output, it signifies that the user wants it to be saved onto their file system, making it accessible beyond the current session. Conversely, leaving an option unselected means that the data will be stored as a memory layer, useful for temporary use within the current session.

    This step is crucial for tailoring the outputs to include only the necessary information, thereby optimising memory usage. By choosing specific outputs to be saved, the user can generate fewer output layers which utilises system resources more efficiently.

    ![Step 4](./img/step-4.png)

2. **Select Outputs**

    There are 5 options available in the select outputs. 

    ![Select options](./img/step-4-1.png)

    **1. NCS With Carbon:** This output is initially unchecked by default. When selected, it triggers the generation of the NCS pathways output, providing insights into the pathways associated with NCS (Natural climate solution) and carbon sequestration.

    **2. Landuse Activity:** Initially, this output is checked by default. It generates landuse activity layer outputs, providing valuable insights into various landuse activities. Users have the option to uncheck it if they do not wish to include landuse data in the report.

    **3. Landuse Activity Normalised:** By default, this output is checked. It generates landuse project normalised outputs, providing a normalised view of landuse activities for enhanced analysis. Users have the option to uncheck it if they do not wish to include landuse normalised data in the report.

    **4. Landuse Activity Weighted with PWL (Priority weighted layers):** By default, this output is checked. It generates landuse projects weighted outputs. Unselecting this option will disable report generation this is because the weighted output is the required output for report generation.

    **5. Scenario Highest Position analysis:** By default, this output is checked. It generates the final highest position analysis outputs. Unselecting this option will disable report generation this is because the highest position analysis output is the required output for report generation.

3. **Processing Options**

    >NOTE: Users need to register and login with a Trends.Earth account to use the online API for processing with CPLUS.

    The user can also choose the processing option, deciding whether they want to process online or offline.

    ![Processing option](./img/step-4-2.png)

    * **Process the scenario online:** By default, this option is unchecked. When the user selects this option, the scenario is processed online using the API. This means that the system sends the scenario data to a remote server or service via the Internet. The remote server performs the necessary computations or analysis based on the provided scenario data. Processing online allows for real-time analysis and can leverage the computing power and resources available on the remote server. This option might be preferred when the user requires quicker results or when the scenario data is too large or complex to be processed efficiently on the user's local device. However, processing online may require a stable internet connection.
   
    *If the user has previously selected `Online defaults`, this option will be selected automatically.*

4. **Scenario report options:** Below are the benefits of the scenario report options.

    * The Metrics Generator enables plugin users to incorporate additional metrics or calculations for each activity. It includes automated expressions that assist in calculating measures such as irrecoverable carbon, financial metrics like the net present value (NPV) of each activity, and other weighting measures such as jobs per hectare.

    * The tool leverages the full functionality of the expression builder, allowing users to create fully customised expressions based on the available project variables.

    * The Expression Builder within the Metrics Generator has been enhanced with a CPLUS library, which offers automated calculations for irrecoverable carbon, PWL measures, and NPV. These features come with helpful guidance for their use. It is also important to reference the variables list when creating custom options.

    >Note: Please note that expressions can be applied on a column-by-column basis or can be cell-specific, providing full granularity for the measures and metrics associated with each activity.

    ![Scenario Reports Options](./img/step-4-7.png)

    1 **Use custom activity metrics table:** Users must check the checkbox to enable this option. After doing so, they need to click on the ![Builder Icon](./img/step-4-8.png) icon to access the metrics table. 

    Users are required to follow these steps to create a custom activity metrics table.

     **Step 1:**

    ![Activity Metrics Wizard](./img/step-4-9.png)

    1 **x:** Close the wizard.

    2 **Help:** Provides the qgis help documentation.

    3 **Back:** Go back to the previous step (Disabled in the first step).

    4 **Next:** Proceed to the next step.

    5 **Cancel:** Cancel the current operation.

    **Step 2:**

    ![Activity Metrics Wizard 2](./img/step-4-10.png)

    1 **Columns:** Users can add or remove columns from the table.

    * **![Add Column](./img/step-4-11.png):** Allows users to add column to the table.

        ![Set Column Name](./img/step-4-12.png)

        * **x:** Close the dialog box.
        * **Input Field:** Users are required to enter the column name in this input field.
        * **Cancel:** Cancel the process.
        * **OK:** Users can complete the add column process by clicking on this button. If users click on this button without filling the column name then the process will be complete without any column being added.

            ![Column Table 1](./img/step-4-14.png)
        
        * If users fill the column name which is already available in the table then the users will encountered with the error `There is already existing column name`.

            ![Duplicate Column Error](./img/step-4-13.png)

    * **![Remove Column](./img/step-4-15.png):** Allows users to remove column from the table. Users are required to select the column which they want to remove from the table and then click on this button to remove it from the table.

        ![Column Table 2](./img/step-4-16.png)

    * **![Up](./img/step-4-17.png) and ![Down](./img/step-4-18.png):** Allows users to reorder the columns in the table. Select the column from the table and then click on the either any option to reorder the column.

    ![Reorder Column](./img/step-4-19.png)

    2 **Properties:** This contains the properties of the column.
    
    ![Properties](./img/step-4-20.png) 

    * **Header label:** The default header name is based on the selected column. Users can change it to any name they prefer, but the field must be filled in. If the `Header label` is empty then the users will encounter with the error `header label is empty`.

        ![Empty Header Label Error](./img/step-4-21.png) 
    
    * **Metric:** Users can select the metric from the dropdown list. User can clear the metric filed by clicking on the `x` mark available inside the input field and can add their own custom metric.

        ![Metric Dropdown](./img/step-4-22.png) 

    * **Create Custom Metric:** Users can create their own custom metric by clicking on the `ε epsilon` button located at the right side of the `Metric` input field.

        ![Epsilon button](./img/step-4-23.png) 

        * This will open the `Column Expression Builder` dialog box.

        ![Column Expression Builder](./img/step-4-24.png)

        1 **Expression:** Users can access the expression tab by clicking here.

        2 **Input Area:** User can enter the expression in this input area.

        3 **Operators and symbols:** Users can access the operators and symbols from here.

        4 **Functions:** Users can choose the function that their expression is related to.

        5 **Details Section:** This section shows the details of the expression like how users can fill the expression, what are the available arguments and operators etc.

        * For Example:

            ![Column Expression Builder 1](./img/step-4-25.png)

            1 **Input Area:** Contains the expression we have entered.

            2 **Functions:** For example, we have selected the `CASE` from `Conditionals`.

            3 **Details Section:** This section shows the details of the expression like how users can fill the expression, what are the available arguments and operators etc.

            4 **Preview:** This section displays the feature details. In our case, we have entered the incorrect input without following the proper syntax, resulting in an error in the preview.

        * After filling all the details users are required to click on the `OK` button to complete the process or they can click on the `Cancel` button to cancel the process.

        * When users click on the `Cancel` button a pop up dialog box will appear asking for confirmation to cancel the process.

            ![Expression Edited](./img/step-4-36.png)

            * **✅:** Users can check this checkbox to remember their choice and avoid showing this message again in the future.

            * **No:** Users can click on the `No` button to go back to the editing the process.

            * **Discard changes:** Users can click on this button to complete the cancel process. This will discard the changes and close the window.

    3 **Formatting:** This contains the formatting options for the column.

    ![Formatting](./img/step-4-26.png)

    * **Horizontal alignment:** Users can select the horizontal alignment of the column from the dropdown list, choosing between left, center, right, or justify alignment.

    * **Format as number:** Users are required to check the checkbox to use this option, then users will be use the `Customise...` button to customise the number format.

        ![Number Formatter ](./img/step-4-27.png)

        1 **Number Format:** Users can use this button to go back to the previous window.

        2 **Category:** Users can select the category of the number format from the dropdown list.

        ![Formatting Category](./img/step-4-28.png)

        3 **Format:** Users can select the format of the number from the dropdown list. (This field varies depending on the selected category.)

        4 **Decimal places:** Users can enter the number of decimal places to be displayed. (This field varies depending on the selected category.)

        5 Show trailing zeros: Users can select this checkbox to display trailing zeros. (This field varies depending on the selected category.)

        6 **Sample:** Users can see the sample of the number format selected.

    **Step 3:**
    
    ![Activity Metrics Wizard 3](./img/step-4-29.png)

    1 **Customise activity metric:** Checking this checkbox allows users to customise the metric of a specific cell.

    2 **Customise cell metric:** Double-clicking on a cell converts it into a dropdown menu. Users can then select the `<Cell metrics>` option from the menu, enabling them to customise the cell metric. 

    ![Cell Metric Dropdown Menu](./img/step-4-30.png)

    * This will open the `Activity Expression Builder` window.

        ![Activity Expression Builder](./img/step-4-31.png)

    Please check the `Step 2` to know more about how to customise the metric.

    * If users try to proceed without defining the `<Cell-metric>` then users will encountered with an error message.

        ![Undefined Error](./img/step-4-32.png)

    **Step 4:**

    This is the last step where user review all the columns and metrics they have defined. After clicking on the `Finish` button will complete the process and redirected to the `Qgis plugin Step 4` from where users can generate the report with the `custom activity metrics table`.

    ![Activity Metrics Wizard 4](./img/step-4-33.png)

5. **Run Scenario:** 

    After checking or unchecking the checkbox, click on the `Run Scenario` button to execute the scenario and generate the report. 

    ![Processing option](./img/step-4-3.png)

    **1. Progress Bar:** Upon clicking this button, a pop-up window will appear, displaying a progress bar indicating the report generation status. 

    **2. View Report Dropdown:** Once the report is generated, the user can click on the `View Report` dropdown, to view the options.

    The following options are available there.

    ![View Report Dropdown](./img/step-4-6.png)

    - **Layout designer:** Opens the report in the QGIS layout designer.

    - **Open PDF:** Opens the created PDF.

    - **Help:** Takes the user to the User's documentation site.
  
    **3. Hide:** This  option hides the Progress Dialog Box.

    **4. Cancel:** Click on the `Cancel` button to terminate the report generation process. Upon clicking this button, it will transform into the `Close` button. Click on the `Close` button to dismiss the pop-up window.

    ### View Task Status Online
    After clicking on the `Hide` button this button will be enabled to view the task status.

    ![View Task Online Button](img/step-4-4.png)

    Click on the `View Task Online button` to view the task status.

    ![Processing Dialog](img/step-4-5.png) 

## Report without custom metrics table

* Users can see in the report there is no custom metrics table.

![Report Without Custom Metrics Table ](img/step-4-35.png)

## Report with custom metrics table

* Users can see in the report that the custom metrics table is included.

![Custom Metrics Table Report](img/step-4-34.png)

Click [here](logs.md) to explore the log section.
