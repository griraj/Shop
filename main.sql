

Drop Trigger if Exists items_trigger on items;
Drop Function if Exists log_item_changes();
Drop Function if Exists encrypt(Varchar, Integer);
Drop Function if Exists decrypt(Varchar, Integer);
Drop Procedure if Exists manage_item(Varchar, Text[]);
Drop Table if Exists items_audit;
Drop Table if Exists items;
Drop Table if Exists categories;

Create Table Categories (
    categoryID Serial Primary Key,
    categoryName Varchar(100) Not Null
);

Create Table Items (
    itemID Serial Primary Key,
    itemName Varchar(100) Not Null,
    price Numeric(10, 2) Not Null,
    stockQuantity Integer Not Null,
    categoryID Integer References Categories(categoryID)
);

Create Table items_audit (
    audit_id Serial Primary Key,
    item_id Integer,
    action_type Varchar(10),
    old_price Numeric(10, 2),
    new_price Numeric(10, 2),
    changed_at Timestamp Default Now()
);

-- Tracks one-off migrations (like the itemname encryption pass) so they
-- can never be silently re-run and double-shift already-encrypted data.
Create Table If Not Exists migration_log (
    migration_name Varchar(50) Primary Key,
    applied_at Timestamp Default Now()
);

Create or Replace Function log_item_changes()
Returns Trigger As $$
Begin
    If TG_OP = 'INSERT' Then
        Insert Into items_audit (item_id, action_type, new_price)
        Values (NEW.itemid, 'INSERT', NEW.price);
        Return NEW;

    Elsif TG_OP = 'UPDATE' Then
        Insert Into items_audit (item_id, action_type, old_price, new_price)
        Values (NEW.itemid, 'UPDATE', OLD.price, NEW.price);
        Return NEW;

    Elsif TG_OP = 'DELETE' Then
        Insert Into items_audit (item_id, action_type, old_price)
        Values (OLD.itemid, 'DELETE', OLD.price);
        Return OLD;
    End If;
End;
$$ Language plpgsql;

Create Trigger items_trigger
After Insert or Update or Delete on Items
For Each Row
Execute Function log_item_changes();

-- p_arr: [1]=itemID, [2]=itemName, [3]=price, [4]=stockQuantity, [5]=categoryID
Create or Replace Procedure manage_item(
    p_operation Varchar,
    p_arr Text[]
)
Language plpgsql
As $$
Declare
    v_itemID Integer;
Begin
    If Nullif(p_arr[1], '') Is Null And Nullif(p_arr[2], '') Is Not Null Then
        Select itemID Into v_itemID From Items Where itemName = p_arr[2];
    Else
        v_itemID := Nullif(p_arr[1], '')::Integer;
    End If;

    If p_operation = 'I' Then
        Insert Into Items (itemName, price, stockQuantity, categoryID)
        Values (
            Nullif(p_arr[2], ''),
            Nullif(p_arr[3], '')::Numeric,
            Nullif(p_arr[4], '')::Integer,
            Nullif(p_arr[5], '')::Integer
        );

    Elsif p_operation = 'U' Then
        Update Items
        Set price = Coalesce(Nullif(p_arr[3], '')::Numeric, price),
            stockQuantity = Coalesce(Nullif(p_arr[4], '')::Integer, stockQuantity),
            categoryID = Coalesce(Nullif(p_arr[5], '')::Integer, categoryID)
        Where itemID = v_itemID;

    Elsif p_operation = 'D' Then
        Delete From Items Where itemID = v_itemID;

    Else
        Raise Exception 'Invalid operation : %', p_operation;
    End If;
End;
$$;

Create or Replace Function encrypt(p_text Varchar, p_shift Integer)
Returns Varchar
Language plpgsql
As $$
Declare
    v_result Varchar := '';
    v_char varchar;
    v_code Integer;
Begin
    For i In 1..Length(p_text) Loop
        v_char := Substring(p_text From i For 1);
        v_code := Ascii(v_char);

        If v_code Between 65 And 90 Then         
            v_result := v_result || Chr(((v_code - 65 + p_shift) % 26 + 26) % 26 + 65);

        Elsif v_code Between 97 And 122 Then       
            v_result := v_result || Chr(((v_code - 97 + p_shift) % 26 + 26) % 26 + 97);

        Else
            v_result := v_result || v_char;        
        End If;
    End Loop;
    Return v_result;
End;
$$;

Create or Replace Function decrypt(p_text Varchar, p_shift Integer)
Returns Varchar
Language plpgsql
As $$
Begin
    Return encrypt(p_text, -p_shift);  
End;
$$;

Insert Into Categories (categoryName) Values ('Electronics');
Insert Into Categories (categoryName) Values ('Groceries');
Insert Into Categories (categoryName) Values ('Stationery');

--Insert Into Items (itemName, price, stockQuantity, categoryID) Values ('Laptop', 85000, 15, 1);
--Insert Into Items (itemName, price, stockQuantity, categoryID) Values ('Charger', 14200, 45, 2);
--Insert Into Items (itemName, price, stockQuantity, categoryID) Values ('NotePad', 4500.50, 70, 3);
--Insert Into Items (itemName, price, stockQuantity, categoryID) Values ('Mobile Phone', 45000, 25, 1);

Call manage_item('I', Array[Null, 'Keyboard', '3200', '30', '1']);
Call manage_item('I', Array[Null, 'Mouse', '2200', '25', '1']);
Call manage_item('U', Array[Null, 'Laptop', '90000']);
Call manage_item('U', Array['3', Null, '5000']);
Call manage_item('D', Array[Null, 'NotePad']);

Select itemName, encrypt(itemName, 5) As hidden_name
From Items;

Select * From categories;
Select * From Items;
Select * From items_audit;