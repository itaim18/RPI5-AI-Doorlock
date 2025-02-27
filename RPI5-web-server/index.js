const express = require("express");
const mongoose = require("mongoose");
const cors = require("cors");
const bodyParser = require("body-parser");

// Initialize Express app
const app = express();
require("dotenv").config();

// Middleware
app.use(cors());
app.use(bodyParser.json());

// Connect to MongoDB Atlas
const dbURI = process.env.MONGO_URI;
MONGO_URL = `mongodb+srv://itaim148:${dbURI}@cluster0.b8vnl.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0`;

mongoose
  .connect(MONGO_URL, { useNewUrlParser: true, useUnifiedTopology: true })
  .then(() => console.log("Connected to MongoDB Atlas"))
  .catch((error) => console.log("MongoDB connection error:", error));

// Define the Item model
const Item = mongoose.model(
  "Item",
  new mongoose.Schema({
    name: { type: String, required: false },
    description: String,
    imageURL: { type: String, required: false }, 
    date: { 
      type: Number,
      default: Date.now
    },
    typeOfEnter: {
      type: String,
      enum: ["resident", "guest", "delivery", "burglar"],
      required: true,
    },
    tags: { type: [String], default: [], required: false },
    residentId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Resident",
      required: false,
    },
  })
);

// CREATE - Add a new item
app.post("/items", async (req, res) => {
  const { name, description, imageURL, typeOfEnter, tags, residentId } = req.body; // Add imageURL to the destructuring
  try {
    const item = new Item({ name, description, imageURL, typeOfEnter, tags, residentId }); // Add imageURL to the new Item
    await item.save();
    res.status(201).send(item);
  } catch (error) {
    res.status(400).send({ error: "Error creating item" });
  }
});
// READ - Get all items with pagination
app.get("/items", async (req, res) => {
  const { page = 1, limit = 20 } = req.query; // Default page = 1, limit = 20

  try {
    const totalItems = await Item.countDocuments(); // Total number of items
    const totalPages = Math.ceil(totalItems / limit); // Total pages based on limit

    // Fetch items with sorting by 'date' in descending order and pagination
    const items = await Item.find()
      .sort({ date: -1 }) // Sort by date in descending order (newest first)
      .skip((page - 1) * limit) // Skip the previous pages' items
      .limit(parseInt(limit)); // Limit the number of items returned

    res.status(200).send({
      metadata: {
        totalItems,
        totalPages,
        currentPage: parseInt(page),
        hasNextPage: page < totalPages,
        hasPreviousPage: page > 1,
      },
      items,
    });
  } catch (error) {
    res.status(500).send({ error: "Error fetching items" });
  }
});



// UPDATE - Update an existing item
app.put("/items/:id", async (req, res) => {
  try {
    const item = await Item.findByIdAndUpdate(req.params.id, req.body, {
      new: true,
    });
    if (!item) {
      return res.status(404).send({ error: "Item not found" });
    }
    res.status(200).send(item);
  } catch (error) {
    res.status(400).send({ error: "Error updating item" });
  }
});

// DELETE - Delete an item
app.delete("/items/:id", async (req, res) => {
  try {
    const item = await Item.findByIdAndDelete(req.params.id);
    if (!item) {
      return res.status(404).send({ error: "Item not found" });
    }
    res.status(200).send({ message: "Item deleted" });
  } catch (error) {
    res.status(400).send({ error: "Error deleting item" });
  }
});

// Start the server
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
